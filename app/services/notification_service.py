"""通知推送服务：PushPlus 微信推送 + Server酱 + SMTP 邮件。"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_pushplus(title: str, content: str) -> bool:
    """通过 PushPlus 推送微信消息。"""
    if not settings.PUSHPLUS_ENABLED or not settings.PUSHPLUS_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "http://www.pushplus.plus/send",
                json={
                    "token": settings.PUSHPLUS_TOKEN,
                    "title": title,
                    "content": content,
                    "template": "txt",
                },
            )
            data = resp.json()
            if data.get("code") == 200:
                logger.info(f"[PushPlus] 推送成功: {title}")
                return True
            logger.warning(f"[PushPlus] 推送失败: {data}")
            return False
    except Exception as e:
        logger.error(f"[PushPlus] 推送异常: {e}")
        return False


async def send_serverchan(title: str, content: str) -> bool:
    """通过 Server酱 推送微信消息。"""
    if not settings.SERVERCHAN_ENABLED or not settings.SERVERCHAN_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://sctapi.ftqq.com/{settings.SERVERCHAN_KEY}.send",
                data={"title": title, "desp": content},
            )
            data = resp.json()
            if data.get("code") == 0:
                logger.info(f"[Server酱] 推送成功: {title}")
                return True
            logger.warning(f"[Server酱] 推送失败: {data}")
            return False
    except Exception as e:
        logger.error(f"[Server酱] 推送异常: {e}")
        return False


async def send_email(title: str, content: str) -> bool:
    """通过 SMTP 发送邮件通知。"""
    if not settings.SMTP_ENABLED or not settings.SMTP_HOST:
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_FROM
        msg["To"] = settings.SMTP_TO
        msg["Subject"] = title
        msg.attach(MIMEText(content, "plain", "utf-8"))

        # Use synchronous smtplib in thread (email is not async-critical)
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_email_sync, msg)
        logger.info(f"[Email] 发送成功: {title}")
        return True
    except Exception as e:
        logger.error(f"[Email] 发送异常: {e}")
        return False


def _send_email_sync(msg: MIMEMultipart):
    """同步发送邮件（在线程池中执行）。"""
    with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        recipients = [addr.strip() for addr in settings.SMTP_TO.split(",")]
        server.sendmail(settings.SMTP_FROM, recipients, msg.as_string())


async def send_notification(title: str, content: str) -> dict:
    """统一通知入口：同时推送到所有已启用的渠道。"""
    results = {}
    results["pushplus"] = await send_pushplus(title, content)
    results["serverchan"] = await send_serverchan(title, content)
    results["email"] = await send_email(title, content)
    sent = sum(1 for v in results.values() if v)
    logger.info(f"[通知] {title} -> {sent}/{len(results)} 渠道成功")
    return results
