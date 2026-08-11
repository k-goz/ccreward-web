"""权益日历与到期提醒服务。

功能：
- 权益使用次数追踪（月度/年度自动重置）
- 权益使用进度查询
- 即将到期的卡片权益提醒
- 年费减免进度追踪
"""

import uuid
import logging
from datetime import date, datetime

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.benefit_usage import BenefitUsageTrack
from app.models.user import UserCard
from app.models.benefit import CardBenefit

logger = logging.getLogger(__name__)

MONTH_FORMAT = "%Y-%m"


def _current_month() -> str:
    return date.today().strftime(MONTH_FORMAT)


def _current_year() -> int:
    return date.today().year


async def _find_or_create_track(
    db: AsyncSession, user_id: str, user_card_id: str, benefit_id: str, benefit_title: str,
) -> BenefitUsageTrack:
    """查找已有追踪记录，没有则新建。"""
    stmt = select(BenefitUsageTrack).where(
        and_(
            BenefitUsageTrack.user_id == user_id,
            BenefitUsageTrack.benefit_id == benefit_id,
            BenefitUsageTrack.user_card_id == user_card_id,
        )
    )
    result = await db.execute(stmt)
    track = result.scalar_one_or_none()
    if not track:
        track = BenefitUsageTrack(
            id=str(uuid.uuid4()),
            user_id=user_id,
            user_card_id=user_card_id,
            benefit_id=benefit_id,
            benefit_title=benefit_title,
        )
        db.add(track)
        await db.flush()
    return track


async def _maybe_reset_monthly(track: BenefitUsageTrack) -> bool:
    """如果跨月则重置月度计数，返回是否发生了重置。"""
    now_month = _current_month()
    if track.last_reset_month != now_month:
        track.used_this_month = 0
        track.last_reset_month = now_month
        return True
    return False


async def _maybe_reset_yearly(track: BenefitUsageTrack) -> bool:
    """如果跨年则重置年度计数，返回是否发生了重置。"""
    now_year = _current_year()
    now_date = date.today()
    last_dt = track.last_used_date
    if last_dt and last_dt.year < now_year:
        track.used_this_year = 0
        return True
    return False


async def track_benefit_usage(
    db: AsyncSession,
    user_id: str,
    user_card_id: str,
    benefit_id: str,
) -> BenefitUsageTrack:
    """记录一次权益使用（不自动+1，仅标记使用日期）。"""
    # 尝试获取权益名称
    benefit = await db.get(CardBenefit, benefit_id)
    benefit_title = benefit.title if benefit else benefit_id

    track = await _find_or_create_track(db, user_id, user_card_id, benefit_id, benefit_title)
    await _maybe_reset_monthly(track)
    await _maybe_reset_yearly(track)
    track.last_used_date = date.today()
    await db.commit()
    await db.refresh(track)
    return track


async def increment_benefit_usage(
    db: AsyncSession,
    user_id: str,
    benefit_id: str,
) -> BenefitUsageTrack:
    """权益使用次数+1，自动处理月度/年度重置。"""
    benefit = await db.get(CardBenefit, benefit_id)
    if not benefit:
        raise ValueError(f"权益不存在: {benefit_id}")

    stmt = select(BenefitUsageTrack).where(
        and_(
            BenefitUsageTrack.user_id == user_id,
            BenefitUsageTrack.benefit_id == benefit_id,
        )
    )
    result = await db.execute(stmt)
    track = result.scalar_one_or_none()

    if not track:
        track = BenefitUsageTrack(
            id=str(uuid.uuid4()),
            user_id=user_id,
            user_card_id="",
            benefit_id=benefit_id,
            benefit_title=benefit.title,
        )
        db.add(track)
        await db.flush()

    await _maybe_reset_monthly(track)
    await _maybe_reset_yearly(track)

    track.used_this_month += 1
    track.used_this_year += 1
    track.total_used += 1
    track.last_used_date = date.today()

    await db.commit()
    await db.refresh(track)
    logger.info(
        f"权益使用+1: user={user_id}, benefit={benefit_id}, "
        f"month={track.used_this_month}/{track.monthly_limit}, "
        f"year={track.used_this_year}/{track.year_limit}"
    )
    return track


async def get_benefit_status(
    db: AsyncSession,
    user_card_id: str,
) -> list[dict]:
    """返回该用户卡下所有权益的使用进度。

    返回列表每项包含：benefit_id, benefit_title, monthly_used, monthly_limit,
    yearly_used, yearly_limit, total_used, last_used_date, is_exhausted。
    """
    stmt = select(BenefitUsageTrack).where(
        and_(
            BenefitUsageTrack.user_card_id == user_card_id,
            BenefitUsageTrack.is_active == True,
        )
    )
    result = await db.execute(stmt)
    tracks = result.scalars().all()

    items = []
    for t in tracks:
        await _maybe_reset_monthly(t)
        await _maybe_reset_yearly(t)
        monthly_exhausted = t.monthly_limit is not None and t.used_this_month >= t.monthly_limit
        yearly_exhausted = t.year_limit is not None and t.used_this_year >= t.year_limit
        items.append({
            "id": t.id,
            "benefit_id": t.benefit_id,
            "benefit_title": t.benefit_title,
            "monthly_used": t.used_this_month,
            "monthly_limit": t.monthly_limit,
            "monthly_exhausted": monthly_exhausted,
            "yearly_used": t.used_this_year,
            "yearly_limit": t.year_limit,
            "yearly_exhausted": yearly_exhausted,
            "total_used": t.total_used,
            "last_used_date": t.last_used_date.isoformat() if t.last_used_date else None,
            "is_exhausted": monthly_exhausted or yearly_exhausted,
        })

    # 排序：未耗尽排前面，已耗尽排后面
    items.sort(key=lambda x: (x["is_exhausted"], -(x["total_used"])))
    return items


async def get_expiring_benefits(
    db: AsyncSession,
    user_id: str,
    days: int = 30,
) -> list[dict]:
    """返回即将到期的权益卡片（expire_date 在未来 days 天内）。

    对于每张即将到期的 user_card，同时返回该卡对应的 credit_card 权益列表。
    """
    today = date.today()
    from datetime import timedelta
    deadline = today + timedelta(days=days)
    deadline_str = deadline.strftime("%Y-%m")

    # 查询到期日在 [today_month, deadline_month] 范围内的 user_cards
    stmt = select(UserCard).where(
        and_(
            UserCard.user_id == user_id,
            UserCard.is_active == True,
            UserCard.expire_date.isnot(None),
            UserCard.expire_date <= deadline_str,
            UserCard.expire_date >= today.strftime("%Y-%m"),
        )
    )
    result = await db.execute(stmt)
    user_cards = result.scalars().all()

    expiring = []
    for uc in user_cards:
        # 计算剩余天数
        try:
            expire_dt = datetime.strptime(uc.expire_date, "%Y-%m").date()
            # 取该月最后一天作为实际到期日
            import calendar
            last_day = calendar.monthrange(expire_dt.year, expire_dt.month)[1]
            expire_end = expire_dt.replace(day=last_day)
            remaining = (expire_end - today).days
        except (ValueError, TypeError):
            remaining = None

        # 获取该卡关联的权益
        card_benefits = []
        if uc.card_id:
            b_stmt = select(CardBenefit).where(
                and_(CardBenefit.card_id == uc.card_id, CardBenefit.is_active == True)
            )
            b_result = await db.execute(b_stmt)
            benefits = b_result.scalars().all()
            card_benefits = [{"id": b.id, "title": b.title, "type": b.benefit_type.value} for b in benefits]

        expiring.append({
            "user_card_id": uc.id,
            "card_id": uc.card_id,
            "nickname": uc.nickname or "",
            "expire_date": uc.expire_date,
            "remaining_days": remaining,
            "is_expired": remaining is not None and remaining < 0,
            "benefits": card_benefits,
        })

    # 按剩余天数升序：快过期的在前面
    expiring.sort(key=lambda x: x["remaining_days"] if x["remaining_days"] is not None else 9999)
    return expiring


async def get_annual_fee_progress(
    db: AsyncSession,
    user_id: str,
) -> list[dict]:
    """年费减免进度追踪。

    统计每位用户各张卡本年的使用次数，与年费减免条件中的刷卡次数要求做对比。
    目前年费条件从 user_cards.annual_fee_condition 中解析。
    """
    import re

    stmt = select(UserCard).where(
        and_(
            UserCard.user_id == user_id,
            UserCard.is_active == True,
        )
    )
    result = await db.execute(stmt)
    user_cards = result.scalars().all()

    progress_list = []
    for uc in user_cards:
        # 统计该卡本年度的总使用次数
        use_stmt = select(func.coalesce(func.sum(BenefitUsageTrack.used_this_year), 0)).where(
            and_(
                BenefitUsageTrack.user_id == user_id,
                BenefitUsageTrack.user_card_id == uc.id,
            )
        )
        use_result = await db.execute(use_stmt)
        current_count = int(use_result.scalar() or 0)

        # 解析年费减免条件中的刷卡次数要求
        required_count: int | None = None
        condition_text = uc.annual_fee_condition or ""
        match = re.search(r"刷[满]?(\d+)\s*[笔次]", condition_text)
        if not match:
            match = re.search(r"(\d+)\s*[笔次]", condition_text)
        if match:
            required_count = int(match.group(1))

        is_waived = uc.annual_fee_waived or False
        if required_count:
            pct = min(100, int(current_count / required_count * 100))
        else:
            pct = 100 if is_waived else 0

        progress_list.append({
            "user_card_id": uc.id,
            "nickname": uc.nickname or "",
            "condition_text": condition_text,
            "required_count": required_count,
            "current_count": current_count,
            "progress_pct": pct,
            "is_waived": is_waived,
            "remaining": max(0, (required_count or 0) - current_count) if required_count else None,
        })

    # 进度低的排前面
    progress_list.sort(key=lambda x: x["progress_pct"])
    return progress_list
