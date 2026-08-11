from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_current_user_optional
from app.database import get_db
from app.services import card_service
from app.schemas.card import CardWithBenefits
from app.schemas.redemption import RedemptionOut

router = APIRouter(prefix="/cards", tags=["信用卡"])


@router.get("", summary="查询信用卡列表")
async def list_cards(
    bank: str | None = Query(None, description="按银行筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_current_user_optional),
) -> dict:
    return await card_service.list_cards(
        db, bank=bank, page=page, page_size=page_size,
    )


@router.get("/{card_id}", summary="查询信用卡详情（含权益）")
async def get_card(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_current_user_optional),
) -> CardWithBenefits:
    card = await card_service.get_card(db, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    return card


@router.get("/{card_id}/redemptions", summary="查询该卡积分可兑换商品")
async def get_card_redemptions(
    card_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_current_user_optional),
) -> list[RedemptionOut]:
    return await card_service.get_card_redemptions(db, card_id=card_id)


@router.get("/user/{user_id}", summary="查询用户持有的信用卡及权益")
async def get_user_cards(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> list[CardWithBenefits]:
    return await card_service.get_user_cards(db, user_id=user_id)


@router.get("/stats/overview", summary="信用卡统计概览")
async def card_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """返回银行数量、卡片数量、权益统计。"""
    return await card_service.get_stats(db)
