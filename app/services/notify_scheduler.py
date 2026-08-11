"""定时通知任务：每天检查账单到期、权益到期并推送。"""
import logging
from datetime import datetime, date, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.config import settings
from app.models.bill import BillRecord
from app.models.benefit_usage import BenefitUsageTrack
from app.services.notification_service import send_notification

logger = logging.getLogger(__name__)


async def check_and_notify():
    """每日通知任务：检查账单到期 + 权益到期 + 年费进度。"""
    logger.info("=== 每日通知任务开始 ===")
    messages = []

    async with async_session() as db:
        # 1. 账单到期提醒（未来3天内到期的）
        bill_msgs = await _check_upcoming_bills(db)
        messages.extend(bill_msgs)

        # 2. 权益到期提醒（30天内到期）
        benefit_msgs = await _check_expiring_benefits(db)
        messages.extend(benefit_msgs)

    if messages:
        title = f"信用卡提醒 ({date.today().strftime('%m/%d')})"
        content = "\n".join(messages)
        await send_notification(title, content)
    else:
        logger.info("[通知] 无需提醒")

    logger.info("=== 每日通知任务完成 ===")


async def _check_upcoming_bills(db: AsyncSession) -> list[str]:
    """检查未来3天内到期的账单。"""
    messages = []
    today = date.today()
    # 查找所有活跃用户卡的未付账单
    result = await db.execute(
        select(BillRecord).where(
            and_(
                BillRecord.is_paid == False,
                BillRecord.due_date >= today.day - 3,
                BillRecord.due_date <= today.day + 3,
            )
        )
    )
    bills = result.scalars().all()
    for bill in bills:
        days_left = (bill.due_date - today).days if isinstance(bill.due_date, date) else 0
        if days_left >= 0:
            messages.append(f"  - 账单到期提醒: 卡 {bill.user_card_id}，还有 {days_left} 天到期还款")
        else:
            messages.append(f"  - 账单已逾期: 卡 {bill.user_card_id}，已逾期 {abs(days_left)} 天")
    return messages


async def _check_expiring_benefits(db: AsyncSession) -> list[str]:
    """检查30天内到期的权益使用追踪。"""
    messages = []
    result = await db.execute(
        select(BenefitUsageTrack).where(
            and_(
                BenefitUsageTrack.is_active == True,
            )
        )
    )
    tracks = result.scalars().all()
    for track in tracks:
        if track.year_limit and track.used_this_year >= track.year_limit:
            messages.append(f"  - 权益已用尽: {track.benefit_title}（年度 {track.used_this_year}/{track.year_limit}）")
        elif track.monthly_limit and track.used_this_month >= track.monthly_limit:
            messages.append(f"  - 权益本月已用尽: {track.benefit_title}（月度 {track.used_this_month}/{track.monthly_limit}）")
    return messages


def register_notify_job(scheduler):
    """在 APScheduler 中注册每日通知任务。"""
    if not (settings.PUSHPLUS_ENABLED or settings.SERVERCHAN_ENABLED or settings.SMTP_ENABLED):
        logger.info("[通知] 所有通知渠道均未启用，跳过注册")
        return

    scheduler.add_job(
        check_and_notify,
        "cron",
        hour=settings.NOTIFY_HOUR,
        minute=settings.NOTIFY_MINUTE,
        id="daily_notify",
        replace_existing=True,
    )
    logger.info(f"[通知] 每日通知任务已注册，{settings.NOTIFY_HOUR:02d}:{settings.NOTIFY_MINUTE:02d} 执行")


def register_benefit_inspection_job(scheduler):
    """在 APScheduler 中注册每周权益巡检任务。"""
    from app.services.benefit_lifecycle_service import run_inspection_and_notify

    scheduler.add_job(
        run_inspection_and_notify,
        "cron",
        day_of_week=settings.BENEFIT_INSPECTION_DAY,
        hour=settings.BENEFIT_INSPECTION_HOUR,
        minute=settings.BENEFIT_INSPECTION_MINUTE,
        id="benefit_inspection",
        replace_existing=True,
    )
    logger.info(
        f"[权益巡检] 定时任务已注册: 每周{settings.BENEFIT_INSPECTION_DAY} "
        f"{settings.BENEFIT_INSPECTION_HOUR:02d}:{settings.BENEFIT_INSPECTION_MINUTE:02d}"
    )
