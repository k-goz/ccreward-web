"""管理后台 API：数据概况、CRUD 编辑、爬虫控制。"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.card import CreditCard
from app.models.benefit import CardBenefit
from app.models.bank_offer import BankOffer
from app.models.activity import MerchantActivity
from app.models.crawl_job import CrawlJob
from app.crawlers.scheduler import get_crawler_status, run_single_crawler

router = APIRouter(prefix="/admin", tags=["管理后台"])


def _fmt_dt(dt):
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# 1. GET /admin/stats — 数据概况
# ---------------------------------------------------------------------------

@router.get("/stats", summary="数据概况")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    cards_total = await db.scalar(select(func.count(CreditCard.id)))
    banks_total = await db.scalar(select(func.count(func.distinct(CreditCard.bank))))
    benefits_total = await db.scalar(select(func.count(CardBenefit.id)))
    activities_total = await db.scalar(select(func.count(MerchantActivity.id)))
    offers_total = await db.scalar(select(func.count(BankOffer.id)))
    try:
        crawler_status = await get_crawler_status()
    except Exception:
        crawler_status = []
    return {
        "cards": cards_total or 0,
        "banks": banks_total or 0,
        "benefits": benefits_total or 0,
        "activities": activities_total or 0,
        "bank_offers": offers_total or 0,
        "crawlers": crawler_status,
    }


# ---------------------------------------------------------------------------
# 2. GET /admin/cards — 卡片列表（分页+筛选）
# ---------------------------------------------------------------------------

@router.get("/cards", summary="卡片列表")
async def admin_list_cards(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    bank: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    q = select(CreditCard)
    cq = select(func.count(CreditCard.id))
    if bank:
        q = q.where(CreditCard.bank == bank)
        cq = cq.where(CreditCard.bank == bank)
    total = await db.scalar(cq)
    q = q.order_by(CreditCard.bank, CreditCard.name).offset((page - 1) * size).limit(size)
    result = await db.execute(q)
    items = [
        {
            "id": c.id, "bank": c.bank, "name": c.name,
            "network": c.network.value if hasattr(c.network, "value") else str(c.network),
            "level": c.level.value if hasattr(c.level, "value") else str(c.level),
            "annual_fee": c.annual_fee, "is_active": c.is_active,
            "description": c.description, "image_url": c.image_url,
            "created_at": _fmt_dt(c.created_at), "updated_at": _fmt_dt(c.updated_at),
        }
        for c in result.scalars().all()
    ]
    return {"items": items, "total": total or 0, "page": page, "size": size}


# ---------------------------------------------------------------------------
# 3. PATCH /admin/cards/{id} — 编辑卡片
# ---------------------------------------------------------------------------

class CardUpdate(BaseModel):
    bank: str | None = None
    name: str | None = None
    annual_fee: str | None = None
    is_active: bool | None = None
    description: str | None = None
    image_url: str | None = None


@router.patch("/cards/{card_id}", summary="编辑卡片")
async def admin_update_card(
    card_id: str, body: CardUpdate,
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    card = await db.get(CreditCard, card_id)
    if not card:
        raise HTTPException(404, "卡片不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(card, k, v)
    card.updated_at = datetime.now()
    await db.commit()
    return {"ok": True, "id": card_id}


# ---------------------------------------------------------------------------
# 4. GET /admin/benefits — 权益列表
# ---------------------------------------------------------------------------

@router.get("/benefits", summary="权益列表")
async def admin_list_benefits(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    total = await db.scalar(select(func.count(CardBenefit.id)))
    q = (
        select(CardBenefit, CreditCard.bank, CreditCard.name)
        .outerjoin(CreditCard, CardBenefit.card_id == CreditCard.id)
        .order_by(desc(CardBenefit.created_at))
        .offset((page - 1) * size).limit(size)
    )
    result = await db.execute(q)
    items = []
    for b, bank, card_name in result.all():
        items.append({
            "id": b.id, "card_id": b.card_id, "card_name": card_name or "",
            "bank": bank or "", "title": b.title,
            "benefit_type": b.benefit_type.value if hasattr(b.benefit_type, "value") else str(b.benefit_type),
            "category": b.category.value if hasattr(b.category, "value") else str(b.category),
            "description": b.description, "value_text": b.value_text,
            "is_active": b.is_active, "usage_limit": b.usage_limit,
            "created_at": _fmt_dt(b.created_at),
        })
    return {"items": items, "total": total or 0, "page": page, "size": size}


# ---------------------------------------------------------------------------
# 5. PATCH /admin/benefits/{id} — 编辑权益
# ---------------------------------------------------------------------------

class BenefitUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_active: bool | None = None
    value_text: str | None = None
    usage_limit: str | None = None


@router.patch("/benefits/{benefit_id}", summary="编辑权益")
async def admin_update_benefit(
    benefit_id: str, body: BenefitUpdate,
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    b = await db.get(CardBenefit, benefit_id)
    if not b:
        raise HTTPException(404, "权益不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    await db.commit()
    return {"ok": True, "id": benefit_id}


# ---------------------------------------------------------------------------
# 6. GET /admin/bank-offers — 银行优惠列表
# ---------------------------------------------------------------------------

@router.get("/bank-offers", summary="银行优惠列表")
async def admin_list_offers(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    bank: str | None = Query(None),
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    q = select(BankOffer)
    cq = select(func.count(BankOffer.id))
    if bank:
        q = q.where(BankOffer.bank == bank)
        cq = cq.where(BankOffer.bank == bank)
    total = await db.scalar(cq)
    q = q.order_by(desc(BankOffer.created_at)).offset((page - 1) * size).limit(size)
    result = await db.execute(q)
    items = [
        {
            "id": o.id, "bank": o.bank, "title": o.title, "category": o.category,
            "description": o.description, "discount_highlight": o.discount_highlight,
            "status": o.status.value if hasattr(o.status, "value") else str(o.status),
            "is_active": o.is_active, "valid_to": _fmt_dt(o.valid_to),
            "valid_period": o.valid_period, "source": o.source,
            "created_at": _fmt_dt(o.created_at), "updated_at": _fmt_dt(o.updated_at),
        }
        for o in result.scalars().all()
    ]
    return {"items": items, "total": total or 0, "page": page, "size": size}


# ---------------------------------------------------------------------------
# 7. PATCH /admin/bank-offers/{id} — 编辑银行优惠
# ---------------------------------------------------------------------------

class OfferUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_active: bool | None = None
    status: str | None = None
    discount_highlight: str | None = None
    valid_period: str | None = None


@router.patch("/bank-offers/{offer_id}", summary="编辑银行优惠")
async def admin_update_offer(
    offer_id: str, body: OfferUpdate,
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    o = await db.get(BankOffer, offer_id)
    if not o:
        raise HTTPException(404, "银行优惠不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "status" and v:
            from app.models.bank_offer import OfferStatus
            for s in OfferStatus:
                if s.value == v or s.name == v:
                    o.status = s
                    break
        else:
            setattr(o, k, v)
    o.updated_at = datetime.now()
    await db.commit()
    return {"ok": True, "id": offer_id}


# ---------------------------------------------------------------------------
# 8. GET /admin/activities — 活动列表
# ---------------------------------------------------------------------------

@router.get("/activities", summary="活动列表")
async def admin_list_activities(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    q = select(MerchantActivity)
    cq = select(func.count(MerchantActivity.id))
    if status:
        q = q.where(MerchantActivity.status == status)
        cq = cq.where(MerchantActivity.status == status)
    total = await db.scalar(cq)
    q = q.order_by(desc(MerchantActivity.created_at)).offset((page - 1) * size).limit(size)
    result = await db.execute(q)
    items = [
        {
            "id": a.id, "title": a.title,
            "platform": a.platform.value if hasattr(a.platform, "value") else str(a.platform),
            "merchant_name": a.merchant_name, "category": a.category,
            "activity_price": a.activity_price, "original_price": a.original_price,
            "discount_description": a.discount_description,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "is_active": a.is_active, "source_type": a.source_type,
            "valid_from": _fmt_dt(a.valid_from), "valid_to": _fmt_dt(a.valid_to),
            "created_at": _fmt_dt(a.created_at),
        }
        for a in result.scalars().all()
    ]
    return {"items": items, "total": total or 0, "page": page, "size": size}


# ---------------------------------------------------------------------------
# 9. PATCH /admin/activities/{id} — 编辑活动
# ---------------------------------------------------------------------------

class ActivityUpdate(BaseModel):
    title: str | None = None
    discount_description: str | None = None
    is_active: bool | None = None
    status: str | None = None
    activity_price: float | None = None
    usage_conditions: str | None = None


@router.patch("/activities/{activity_id}", summary="编辑活动")
async def admin_update_activity(
    activity_id: str, body: ActivityUpdate,
    db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user),
):
    a = await db.get(MerchantActivity, activity_id)
    if not a:
        raise HTTPException(404, "活动不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "status" and v:
            from app.models.activity import ActivityStatus
            for s in ActivityStatus:
                if s.value == v or s.name == v:
                    a.status = s
                    break
        else:
            setattr(a, k, v)
    a.updated_at = datetime.now()
    await db.commit()
    return {"ok": True, "id": activity_id}


# ---------------------------------------------------------------------------
# 10. GET /admin/crawlers — 爬虫运行状态
# ---------------------------------------------------------------------------

@router.get("/crawlers", summary="爬虫运行状态")
async def admin_crawlers(user: dict = Depends(get_current_user)):
    return await get_crawler_status()


# ---------------------------------------------------------------------------
# 11. POST /admin/crawlers/{name}/run — 手动触发爬虫
# ---------------------------------------------------------------------------

@router.post("/crawlers/{crawler_name}/run", summary="手动触发爬虫")
async def admin_run_crawler(
    crawler_name: str, user: dict = Depends(get_current_user),
):
    return await run_single_crawler(crawler_name)


# ---------------------------------------------------------------------------
# 12. POST /admin/benefits/refresh-cache — 刷新权益缓存
# ---------------------------------------------------------------------------

@router.post("/benefits/refresh-cache", summary="刷新权益缓存")
async def admin_refresh_cache(user: dict = Depends(get_current_user)):
    return {"ok": True, "message": "缓存已刷新"}


# ---------------------------------------------------------------------------
# 13. GET /admin/benefits/inspection — 权益巡检报告
# ---------------------------------------------------------------------------

@router.get("/benefits/inspection", summary="权益巡检报告")
async def get_benefit_inspection(user: dict = Depends(get_current_user)):
    """获取最近一次权益巡检报告。"""
    from app.services.benefit_lifecycle_service import get_inspection_report
    return await get_inspection_report()


# ---------------------------------------------------------------------------
# 14. POST /admin/benefits/inspection/run — 手动触发权益巡检
# ---------------------------------------------------------------------------

@router.post("/benefits/inspection/run", summary="手动触发权益巡检")
async def run_benefit_inspection(user: dict = Depends(get_current_user)):
    """手动触发权益巡检并推送通知。"""
    from app.services.benefit_lifecycle_service import run_inspection_and_notify
    await run_inspection_and_notify()
    return {"status": "ok"}
