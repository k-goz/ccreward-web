"""推荐 & 多卡对比 API"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.services import recommend_service, compare_service

router = APIRouter(prefix="/recommend", tags=["推荐 & 对比"])


@router.get("/scenario", summary="场景推荐")
async def recommend(
    scenario: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """根据场景关键词推荐最合适信用卡（含匹配权益 + 推荐理由）。"""
    return await recommend_service.recommend_cards(scenario, db, user_id=user["user_id"])


@router.get("/compare", summary="多卡对比")
async def compare(
    card_ids: str,
    scenario: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """横向对比多张信用卡，按场景筛选权益并排对比，给出胜出推荐。"""
    ids = card_ids.split(",")
    return await compare_service.compare_cards(ids, scenario, db)
