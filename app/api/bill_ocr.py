"""账单截图 OCR 识别服务。

POST /api/bill-ocr/upload
  multipart/form-data { file: image }
  → 百度 OCR 通用文字识别（优先）/ Tesseract（回退）
  → 正则提取：金额 / 商户名 / 日期
  → 返回 {"amount": float, "merchant": str, "date": str, "raw_text": str, "confidence": int}
"""

import io
import re
import os
import base64
import logging
from datetime import date, datetime

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException

from app.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bill-ocr", tags=["账单OCR识别"])

# ── 支付平台关键词 ───────────────────────────────
PAYMENT_PLATFORMS = [
    "支付宝", "微信支付", "微信", "美团", "大众点评",
    "饿了么", "京东", "淘宝", "天猫", "拼多多",
    "滴滴", "抖音", "快手", "Apple Pay", "银联",
    "云闪付", "PayPal", "花呗", "白条",
]

# ── 商户关键词（通过特定模式提取）─────────────────
MERCHANT_PREFIXES = [
    r"商户[：:]\s*(.{2,30})",
    r"收款方[：:]\s*(.{2,30})",
    r"付款商户[：:]\s*(.{2,30})",
    r"对方[：:]\s*(.{2,30})",
    r"收款账户[：:]\s*(.{2,30})",
    r"交易对手[：:]\s*(.{2,30})",
    r"收款人[：:]\s*(.{2,30})",
    r"付款商户全称[：:]\s*(.{2,30})",
    r"付款说明[：:]\s*(.{2,30})",
    r"商品说明[：:]\s*(.{2,30})",
    r"商品名称[：:]\s*(.{2,30})",
    r"收款账户名称[：:]\s*(.{2,30})",
    r"对方账户名称[：:]\s*(.{2,30})",
    r"<商户名称>(.{2,30})<",
    r"收款商户[：:]\s*(.{2,30})",
]


def _baidu_general_ocr(image_bytes: bytes) -> str:
    """使用百度 OCR 通用文字识别 API 提取文本。"""
    api_key = os.environ.get("BAIDU_OCR_API_KEY", "")
    secret_key = os.environ.get("BAIDU_OCR_SECRET_KEY", "")

    if not api_key or not secret_key:
        raise RuntimeError("百度 OCR API 未配置")

    import requests

    # Get access token
    token_url = (
        f"https://aip.baidubce.com/oauth/2.0/token?"
        f"grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
    )
    resp = requests.get(token_url, timeout=10)
    resp.raise_for_status()
    token_data = resp.json()
    if "access_token" not in token_data:
        raise RuntimeError(f"获取百度 access token 失败: {token_data}")

    access_token = token_data["access_token"]

    # Resize if needed
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes))
    max_w = 2000
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=85)
    compressed = buf.getvalue()

    if len(compressed) > 3 * 1024 * 1024:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=55)
        compressed = buf.getvalue()

    # Call general OCR
    img_base64 = base64.b64encode(compressed).decode("utf-8")
    ocr_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={access_token}"
    params = {"image": img_base64, "language_type": "CHN_ENG", "detect_direction": "true"}

    resp = requests.post(ocr_url, data=params, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    if "error_code" in result:
        raise RuntimeError(f"百度 OCR 错误 {result.get('error_code')}: {result.get('error_msg')}")

    words = []
    for item in result.get("words_result", []):
        words.append(item.get("words", ""))

    return "\n".join(words)


def _tesseract_ocr(image_bytes: bytes) -> str:
    """使用 Tesseract 进行通用文字识别。"""
    import pytesseract
    from PIL import Image, ImageEnhance

    img = Image.open(io.BytesIO(image_bytes))

    max_w = 2000
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

    gray = img.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(1.3)

    configs = [
        r'--oem 3 --psm 6 -l chi_sim+eng',
        r'--oem 3 --psm 3 -l chi_sim+eng',
    ]

    for cfg in configs:
        text = pytesseract.image_to_string(gray, config=cfg)
        if len(text.strip()) > 10:
            return text.strip()

    return pytesseract.image_to_string(gray, config=r'--oem 3 --psm 6 -l chi_sim+eng')


def _extract_amounts(text: str) -> list[dict]:
    """从 OCR 文本中提取金额信息。"""
    results = []

    # Pattern 1: ￥123.45 or ¥123.45
    for m in re.finditer(r'(?:[¥￥]|CNY)\s*(\d{1,6}\.?\d{0,2})', text):
        amt = float(m.group(1))
        if 0 < amt < 500000:
            results.append({"amount": amt, "pos": m.start(), "source": "currency_symbol"})

    # Pattern 2: 金额: 123.45 or 消费: 123.45
    for m in re.finditer(r'(?:金额|消费|支付|付款|实付|合计|总计|实收|扣款)[：:]\s*(\d{1,6}\.?\d{0,2})', text):
        amt = float(m.group(1))
        if 0 < amt < 500000:
            results.append({"amount": amt, "pos": m.start(), "source": "amount_label"})

    # Pattern 3: -123.45 or -¥123.45 (debit notation)
    for m in re.finditer(r'[-−]\s*(?:[¥￥])?\s*(\d{1,6}\.?\d{0,2})', text):
        amt = float(m.group(1))
        if 0 < amt < 500000:
            results.append({"amount": amt, "pos": m.start(), "source": "debit_notation"})

    # Pattern 4: standalone amount with 2 decimal places (last resort)
    for m in re.finditer(r'\b(\d{1,6}\.\d{2})\b', text):
        amt = float(m.group(1))
        if 5 < amt < 100000:
            results.append({"amount": amt, "pos": m.start(), "source": "standalone_decimal"})

    return results


def _extract_merchant(text: str) -> str:
    """从 OCR 文本中提取商户名称。"""
    # Try specific merchant label patterns first
    for pattern in MERCHANT_PREFIXES:
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip()
            name = re.sub(r'[（\(][^)）]*[）\)]', '', name)  # Remove parenthetical notes
            if len(name) >= 2 and not name.upper().startswith("CNY"):
                return name

    # Find payment platform mentions (highest confidence line)
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        for platform in PAYMENT_PLATFORMS:
            if platform in line:
                # Extract the rest of the line as potential merchant
                clean = line.replace(platform, "").strip()
                clean = re.sub(r'[（(][^)）]*[)）]', '', clean)
                clean = re.sub(r'^[^\w\u4e00-\u9fff]+', '', clean)
                if len(clean) >= 2:
                    return clean
                return platform

    # Try to find a likely merchant name (Chinese words of 2-8 chars)
    merchant_like = re.findall(r'[\u4e00-\u9fffA-Za-z&·]+(?:\([^)]+\))?[\u4e00-\u9fffA-Za-z&·]*', text)
    exclude = {"支付宝", "微信支付", "微信", "交易", "支付", "付款", "收款",
               "退款", "账单", "明细", "金额", "时间", "日期", "商户",
               "消费", "成功", "余额", "花呗", "信用卡", "储蓄卡"}
    for candidate in merchant_like:
        candidate = candidate.strip()
        if 2 <= len(candidate) <= 15 and candidate not in exclude:
            return candidate

    return ""


def _extract_date(text: str) -> str:
    """从 OCR 文本中提取日期。"""
    # Pattern 1: YYYY-MM-DD or YYYY/MM/DD
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', text)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        if 2020 <= int(y) <= 2030 and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{mo}-{d}"

    # Pattern 2: MM-DD or MM/DD (Chinese format)
    m = re.search(r'(\d{1,2})[-/](\d{1,2})', text)
    if m:
        mo, d = m.group(1).zfill(2), m.group(2).zfill(2)
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31:
            today = date.today()
            return f"{today.year}-{mo}-{d}"

    # Pattern 3: 日期: YYYY-MM-DD or 交易时间: YYYY-MM-DD HH:MM
    for label in ["日期", "交易日期", "消费日期", "付款日期", "交易时间", "付款时间",
                   "消费时间", "交易时间"]:
        m = re.search(rf'{label}[：:]\s*(\d{{4}})[-/](\d{{1,2}})[-/](\d{{1,2}})', text)
        if m:
            y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
            if 2020 <= int(y) <= 2030:
                return f"{y}-{mo}-{d}"

    # Pattern 4: Chinese date: 2024年12月25日
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        if 2020 <= int(y) <= 2030:
            return f"{y}-{mo}-{d}"

    return date.today().isoformat()


def ocr_bill_text(text: str) -> dict:
    """从 OCR 文本中提取账单信息。"""
    text = text.strip()
    if not text:
        return {
            "amount": 0.0,
            "merchant": "",
            "date": date.today().isoformat(),
            "raw_text": "",
            "confidence": 0,
        }

    amounts = _extract_amounts(text)
    merchant = _extract_merchant(text)
    detected_date = _extract_date(text)

    # Pick the best amount: prefer amount_label > currency_symbol > standalone
    best_amount = 0.0
    amount_source = "none"
    for priority_source in ["amount_label", "currency_symbol", "debit_notation", "standalone_decimal"]:
        candidates = [a for a in amounts if a["source"] == priority_source]
        if candidates:
            # Take the largest one that's reasonable (the total/receipt amount)
            best_amount = max(a["amount"] for a in candidates)
            amount_source = priority_source
            break

    # Confidence calculation
    confidence = 0
    if best_amount > 0:
        confidence += 35
        if amount_source in ("amount_label", "currency_symbol"):
            confidence += 15
    if merchant:
        confidence += 30
        if any(p in merchant for p in PAYMENT_PLATFORMS):
            confidence += 5
    if detected_date and detected_date != date.today().isoformat():
        confidence += 20
    else:
        confidence += 5  # Fallback to today is still partially useful

    # Parse detected_date to date type for comparison
    try:
        parsed_date = datetime.strptime(detected_date, "%Y-%m-%d").date()
    except ValueError:
        parsed_date = date.today()

    return {
        "amount": round(best_amount, 2),
        "merchant": merchant,
        "date": detected_date,
        "raw_text": text[:500],
        "confidence": min(confidence, 100),
    }


@router.post("/upload", summary="上传账单截图进行OCR识别")
async def upload_bill_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
) -> dict:
    """
    上传账单截图，OCR 识别后返回提取的金额、商户、日期。

    优先级：百度 OCR 通用文字识别 → Tesseract 回退
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件（jpg/png）")

    try:
        image_bytes = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="读取上传文件失败")

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="上传文件为空")

    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片文件大小不能超过 10MB")

    # Try Baidu OCR first, fallback to Tesseract
    text = ""
    source = "none"
    try:
        text = _baidu_general_ocr(image_bytes)
        source = "baidu_ocr"
        logger.info(f"Baidu OCR succeeded: {len(text)} chars")
    except Exception as e:
        logger.warning(f"Baidu OCR failed: {e}, trying Tesseract...")
        try:
            text = _tesseract_ocr(image_bytes)
            source = "tesseract"
            logger.info(f"Tesseract OCR succeeded: {len(text)} chars")
        except Exception as e2:
            logger.error(f"Tesseract OCR also failed: {e2}")
            raise HTTPException(status_code=500, detail=f"OCR 识别失败: {str(e2)}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="未能从图片中识别到文字，请确保截图清晰完整")

    result = ocr_bill_text(text)
    result["source"] = source
    logger.info(f"Bill OCR result: amount={result['amount']}, merchant={result['merchant']}, confidence={result['confidence']}")

    return result
