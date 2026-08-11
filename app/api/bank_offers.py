"""银行优惠 API：各行信用卡实时优惠活动，支持筛选/搜索/按我的卡匹配。"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user_optional
from app.models.bank_offer import BankOffer, OfferStatus
from app.models.user import UserCard
from app.models.card import CreditCard
from app.services.bank_offer_service import get_inspection_report

router = APIRouter(prefix="/bank-offers", tags=["银行优惠"])


def _status_str(o: BankOffer) -> str:
    return o.status.value if isinstance(o.status, OfferStatus) else str(o.status)


def _offer_to_dict(o: BankOffer) -> dict:
    return {
        "id": o.id,
        "bank": o.bank,
        "title": o.title,
        "category": o.category,
        "description": o.description,
        "discount_highlight": o.discount_highlight,
        "how_to_join": o.how_to_join,
        "jump_url": o.jump_url,
        "valid_period": o.valid_period,
        "valid_to": o.valid_to.isoformat() if o.valid_to else None,
        "status": _status_str(o),
        "applicable_cards": o.applicable_cards,
        "source": o.source,
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }


def _effective_status(o: BankOffer) -> str:
    """限时活动到期后自动视为已过期。"""
    if _status_str(o) == OfferStatus.ACTIVE.value and o.valid_to and o.valid_to < datetime.now():
        return OfferStatus.EXPIRED.value
    return _status_str(o)


@router.get("", summary="银行优惠列表")
async def list_offers(
    bank: str | None = Query(None, description="按银行筛选"),
    category: str | None = Query(None, description="按分类筛选"),
    keyword: str | None = Query(None, description="搜索关键词"),
    status: str | None = Query(None, description="进行中/常态活动/已过期"),
    my_banks: bool = Query(False, description="只看我持卡银行的优惠"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_current_user_optional),
) -> dict:
    q = select(BankOffer).where(BankOffer.is_active == True)

    user_banks: set[str] = set()
    if my_banks:
        if not user:
            return {"total": 0, "items": [], "banks": []}
        r = await db.execute(
            select(CreditCard.bank)
            .join(UserCard, UserCard.card_id == CreditCard.id)
            .where(UserCard.user_id == user["user_id"], UserCard.is_active == True)
        )
        user_banks = {row[0] for row in r.all()}
        if not user_banks:
            return {"total": 0, "items": [], "banks": []}
        q = q.where(BankOffer.bank.in_(user_banks))

    if bank:
        q = q.where(BankOffer.bank == bank)
    if category:
        q = q.where(BankOffer.category == category)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(or_(
            BankOffer.title.ilike(like),
            BankOffer.description.ilike(like),
            BankOffer.bank.ilike(like),
        ))

    offers = (await db.execute(q.order_by(BankOffer.updated_at.desc()))).scalars().all()
    # 过期判定后再按状态筛选
    offers = [o for o in offers if not status or _effective_status(o) == status]
    # 进行中/常态优先，过期沉底
    order = {OfferStatus.ACTIVE.value: 0, OfferStatus.REGULAR.value: 1, OfferStatus.EXPIRED.value: 2}
    offers.sort(key=lambda o: order.get(_effective_status(o), 9))

    total = len(offers)
    items = offers[(page - 1) * page_size: page * page_size]
    result = [_offer_to_dict(o) for o in items]
    for it in result:
        it["status"] = next(_effective_status(o) for o in items if o.id == it["id"])
    return {"total": total, "items": result}


@router.get("/banks", summary="有优惠的银行列表")
async def list_banks(db: AsyncSession = Depends(get_db)) -> list[dict]:
    r = await db.execute(
        select(BankOffer.bank, func.count(BankOffer.id))
        .where(BankOffer.is_active == True)
        .group_by(BankOffer.bank)
        .order_by(func.count(BankOffer.id).desc())
    )
    return [{"bank": row[0], "count": row[1]} for row in r.all()]


@router.get("/categories", summary="优惠分类列表")
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[dict]:
    r = await db.execute(
        select(BankOffer.category, func.count(BankOffer.id))
        .where(BankOffer.is_active == True)
        .group_by(BankOffer.category)
        .order_by(func.count(BankOffer.id).desc())
    )
    return [{"category": row[0], "count": row[1]} for row in r.all()]


@router.get("/stats", summary="银行优惠统计")
async def offer_stats(db: AsyncSession = Depends(get_db)) -> dict:
    total = (await db.execute(
        select(func.count(BankOffer.id)).where(BankOffer.is_active == True)
    )).scalar() or 0
    banks = (await db.execute(
        select(func.count(func.distinct(BankOffer.bank))).where(BankOffer.is_active == True)
    )).scalar() or 0
    return {"total_offers": total, "total_banks": banks}


@router.get("/inspection", summary="银行优惠巡检报告")
async def offer_inspection_report() -> dict:
    """获取最近一次巡检结果：过期数、新增失效、需人工确认、建议操作。"""
    return await get_inspection_report()
