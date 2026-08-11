"""权益日历与到期提醒 API。"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.services import reminder_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reminders", tags=["权益日历与提醒"])


@router.get("/usage/{user_card_id}", summary="权益使用进度")
async def benefit_usage_status(
    user_card_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回指定用户卡下所有权益的使用进度（已用/限额）。"""
    return await reminder_service.get_benefit_status(db, user_card_id=user_card_id)


@router.post("/usage/{benefit_id}/use", summary="记录使用+1")
async def record_benefit_usage(
    benefit_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """记录一次权益使用，自动处理月度/年度计数重置。

    返回更新后的使用状态（已用次数/限额/是否耗尽）。
    """
    try:
        track = await reminder_service.increment_benefit_usage(db, user_id=user["user_id"], benefit_id=benefit_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    monthly_exhausted = track.monthly_limit is not None and track.used_this_month >= track.monthly_limit
    yearly_exhausted = track.year_limit is not None and track.used_this_year >= track.year_limit
    return {
        "benefit_id": track.benefit_id,
        "benefit_title": track.benefit_title,
        "monthly_used": track.used_this_month,
        "monthly_limit": track.monthly_limit,
        "monthly_exhausted": monthly_exhausted,
        "yearly_used": track.used_this_year,
        "yearly_limit": track.year_limit,
        "yearly_exhausted": yearly_exhausted,
        "total_used": track.total_used,
        "last_used_date": track.last_used_date.isoformat() if track.last_used_date else None,
        "is_exhausted": monthly_exhausted or yearly_exhausted,
    }


@router.get("/expiring", summary="即将到期的权益和卡片")
async def expiring_benefits(
    user: dict = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365, description="提前多少天提醒"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回指定用户所有在未来 days 天内到期的卡片及权益。"""
    return await reminder_service.get_expiring_benefits(db, user_id=user["user_id"], days=days)


@router.get("/annual-fee", summary="年费减免进度")
async def annual_fee_progress(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回指定用户各张卡的年费减免进度（刷卡次数 vs 次数要求）。"""
    return await reminder_service.get_annual_fee_progress(db, user_id=user["user_id"])
