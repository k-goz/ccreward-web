"""Baidu OCR bank card recognition service."""
import base64
import os
import io
import asyncio
import requests
from PIL import Image

BANK_CARD_TYPE_MAP = {0: "未知", 1: "借记卡", 2: "信用卡"}


def get_access_token(api_key: str, secret_key: str) -> str:
    """Get Baidu API access token."""
    url = (
        f"https://aip.baidubce.com/oauth/2.0/token?"
        f"grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise Exception(f"Failed to get access token: {data}")
    return data["access_token"]


def recognize_bank_card_sync(image_bytes: bytes, api_key: str, secret_key: str) -> dict:
    """Recognize bank card using Baidu OCR API (sync)."""
    access_token = get_access_token(api_key, secret_key)
    img_base64 = base64.b64encode(image_bytes).decode("utf-8")
    
    url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/bankcard?access_token={access_token}"
    params = {"image": img_base64, "show": "true"}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    resp = requests.post(url, data=params, headers=headers, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    
    if "error_code" in result:
        raise Exception(f"Baidu OCR error: {result.get('error_code')} - {result.get('error_msg')}")
    
    if "result" not in result:
        return {"card_number": "", "bank_name": "", "card_type": "", "valid_date": "", "confidence": 0}
    
    r = result["result"]
    card_number = r.get("bank_card_number", "")
    bank_name = r.get("bank_name", "")
    card_type_num = r.get("bank_card_type", 0)
    card_type = BANK_CARD_TYPE_MAP.get(card_type_num, "未知")
    valid_date = r.get("valid_date", "")
    
    fields_filled = sum(1 for v in [card_number, bank_name, valid_date] if v)
    confidence = int(fields_filled / 3 * 100)
    
    return {
        "card_number": card_number,
        "bank_name": bank_name,
        "card_type": card_type,
        "valid_date": valid_date,
        "confidence": confidence,
    }


async def recognize_card(image_bytes: bytes) -> dict:
    """
    Main async entry point. Reads API keys from environment.
    Returns structured card data matching the frontend expectations.
    """
    api_key = os.environ.get("BAIDU_OCR_API_KEY", "")
    secret_key = os.environ.get("BAIDU_OCR_SECRET_KEY", "")
    
    if not api_key or not secret_key:
        # Fallback to Tesseract if Baidu keys not configured
        from app.services.card_ocr_service import recognize_card as tesseract_recognize
        return await tesseract_recognize(image_bytes)
    
    loop = asyncio.get_event_loop()
    
    # Preprocess image
    img = Image.open(io.BytesIO(image_bytes))
    if img.width > 2000:
        ratio = 2000 / img.width
        img = img.resize((2000, int(img.height * ratio)), Image.LANCZOS)
    
    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=85)
    image_bytes = buf.getvalue()
    
    if len(image_bytes) > 3 * 1024 * 1024:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
        image_bytes = buf.getvalue()
    
    # Call Baidu OCR
    result = await loop.run_in_executor(
        None, recognize_bank_card_sync, image_bytes, api_key, secret_key
    )
    
    # Format valid_date to YYYY-MM
    valid_date = result.get("valid_date", "")
    formatted_date = ""
    if valid_date:
        valid_date = valid_date.replace(" ", "")
        if "/" in valid_date:
            parts = valid_date.split("/")
            if len(parts) == 2:
                month, year = parts
                if len(year) == 2:
                    year = "20" + year
                formatted_date = f"{year}-{month.zfill(2)}"
        elif len(valid_date) == 6 and valid_date.isdigit():
            year = valid_date[:4]
            month = valid_date[4:]
            if int(year) > 2000:
                formatted_date = f"{year}-{month}"
            else:
                formatted_date = f"20{year}-{month}"
        elif len(valid_date) == 4 and valid_date.isdigit():
            month = valid_date[:2]
            year = "20" + valid_date[2:]
            formatted_date = f"{year}-{month}"
    
    # Map last 4 digits
    card_number = result.get("card_number", "").replace(" ", "")
    last_four = card_number[-4:] if len(card_number) >= 4 else card_number
    
    return {
        "card_number": card_number,
        "last_four": last_four,
        "bank_name": result.get("bank_name", ""),
        "card_type": result.get("card_type", ""),
        "valid_date": formatted_date,
        "cardholder_name": "",
        "confidence": result.get("confidence", 0),
        "source": "baidu_ocr",
    }
