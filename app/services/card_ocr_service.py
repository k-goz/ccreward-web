"""信用卡 OCR 识别服务：通过 Tesseract 识别卡面信息。"""
import io
import re
import logging

logger = logging.getLogger(__name__)

# 银行 BIN 号前缀映射（简化版，覆盖主流银行）
BANK_BIN_MAP = {
    "622202": "工商银行", "622230": "工商银行", "621226": "工商银行",
    "622848": "农业银行", "622830": "农业银行", "625996": "农业银行",
    "621661": "中国银行", "621660": "中国银行", "622760": "中国银行",
    "622700": "建设银行", "621700": "建设银行", "622280": "建设银行",
    "622575": "招商银行", "622588": "招商银行", "622576": "招商银行",
    "621483": "招商银行",
    "622161": "交通银行", "622260": "交通银行", "622233": "交通银行",
    "622688": "中信银行", "622690": "中信银行", "622689": "中信银行",
    "622660": "光大银行", "622665": "光大银行", "622655": "光大银行",
    "622622": "民生银行", "622625": "民生银行", "622620": "民生银行",
    "622908": "兴业银行", "622909": "兴业银行", "622918": "兴业银行",
    "622568": "广发银行", "622555": "广发银行", "622556": "广发银行",
    "622151": "邮储银行", "622150": "邮储银行", "622188": "邮储银行",
    "622302": "平安银行", "622303": "平安银行", "622168": "平安银行",
    "622516": "浦发银行", "622521": "浦发银行", "622518": "浦发银行",
    "622630": "华夏银行",
    "622228": "上海银行", "622468": "上海银行",
    "622278": "北京银行", "622238": "北京银行",
    "622232": "南京银行",
    "622223": "杭州银行", "622426": "杭州银行",
    "622203": "江苏银行", "622235": "江苏银行",
    "622226": "宁波银行", "622229": "宁波银行",
}


async def recognize_card(image_bytes: bytes) -> dict:
    """识别信用卡图片，返回识别结果。"""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return {"error": "OCR 依赖未安装，请安装 pytesseract 和 Pillow"}

    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        # 压缩大图
        max_w = 2000
        if image.width > max_w:
            ratio = max_w / image.width
            image = image.resize((max_w, int(image.height * ratio)), Image.LANCZOS)

        # 多轮识别，取最佳结果
        from PIL import ImageEnhance, ImageOps
        all_texts = []
        
        # 方式1: 灰度 + 对比度增强 + PSM 6
        gray = image.convert("L")
        gray = ImageEnhance.Contrast(gray).enhance(1.3)
        cfg6 = r'--oem 3 --psm 6'
        t1 = pytesseract.image_to_string(gray, lang="eng", config=cfg6)
        all_texts.append(t1)
        
        # 方式2: 二值化 + PSM 11（稀疏文本模式）
        binary = gray.point(lambda x: 0 if x < 128 else 255, '1')
        cfg11 = r'--oem 3 --psm 11'
        t2 = pytesseract.image_to_string(binary, lang="eng", config=cfg11)
        all_texts.append(t2)
        
        # 方式3: 反色（适合浅色字深色底的卡面）
        inverted = ImageOps.invert(gray)
        t3 = pytesseract.image_to_string(inverted, lang="eng", config=cfg6)
        all_texts.append(t3)
        
        # 选择包含最多数字的结果
        def count_digits(s):
            return sum(1 for c in s if c.isdigit())
        
        raw_text = max(all_texts, key=count_digits)
        logger.info(f"OCR best text ({count_digits(raw_text)} digits): {raw_text[:200]}")
        logger.info(f"OCR raw text: {raw_text[:200]}")
        
        result = {
            "card_number": "",
            "last_four": "",
            "expiry_date": "",
            "expire_month": "",
            "expire_year": "",
            "bank_name": "",
            "cardholder_name": "",
            "raw_text": raw_text.strip(),
            "confidence": 0,
        }
        
        # 1. 提取卡号
        card_patterns = [
            r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b',
            r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{3})\b',
        ]
        for pattern in card_patterns:
            match = re.search(pattern, raw_text.replace('\n', ' '))
            if match:
                card_num = re.sub(r'[\s\-]', '', match.group(1))
                if len(card_num) >= 15:
                    result["card_number"] = card_num
                    result["last_four"] = card_num[-4:]
                    for bin_prefix, bank in BANK_BIN_MAP.items():
                        if card_num.startswith(bin_prefix):
                            result["bank_name"] = bank
                            break
                    break
        
        # 2. 提取有效期（多种格式）
        clean = raw_text.replace('\n', ' ')
        expiry_patterns = [
            r'(?:valid\s*thru|exp(?:iry)?|thru|good\s*thru)[^\d]*(\d{1,2})\s*[/\-\.]\s*(\d{2,4})',
            r'(\d{1,2})\s*[/\-\.]\s*(\d{2,4})(?=\s*(?:valid|exp|CVD|CVV|$))',
            r'\b(\d{1,2})\s*[/\-\.]\s*(\d{2,4})\b',
        ]
        for pattern in expiry_patterns:
            match = re.search(pattern, clean, re.IGNORECASE)
            if match:
                month, year = match.group(1).zfill(2), match.group(2)
                if 1 <= int(month) <= 12:
                    result["expiry_date"] = f"{month}/{year}"
                    result["expire_month"] = month
                    result["expire_year"] = f"20{year}" if len(year) == 2 else year
                    break
        
        # 3. 提取持卡人（支持多种格式）
        name_patterns = [
            r'\b([A-Z]{2,}(?:\s+[A-Z]{2,})+)\b',
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b',
        ]
        skip_words = {'valid', 'thru', 'month', 'year', 'gold', 'platinum',
                      'bank', 'china', 'card', 'credit', 'debit', 'international'}
        for pattern in name_patterns:
            name_match = re.search(pattern, raw_text)
            if name_match:
                name = name_match.group(1).strip()
                words = set(name.lower().split())
                if not words & skip_words:
                    result["cardholder_name"] = name
                    break
        
        # 4. 置信度
        conf = 0
        if result["card_number"]: conf += 40
        if result["expiry_date"]: conf += 30
        if result["bank_name"]: conf += 20
        if result["cardholder_name"]: conf += 10
        result["confidence"] = conf
        
        return result
        
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return {"error": f"识别失败: {str(e)}", "raw_text": ""}
