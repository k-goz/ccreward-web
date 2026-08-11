"""用户服务层：卡片管理（我的卡包）、收藏、搜索历史。"""

import uuid
from datetime import datetime
from math import ceil

from sqlalchemy import select, delete, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.card import CreditCard
from app.models.user import UserCard
from app.models.user_favorite import UserFavorite, UserSearchHistory
from app.schemas.card import CardWithBenefits


# --- 我的卡包 ---

async def list_user_cards(db: AsyncSession, user_id: str) -> list[dict]:
    """返回用户持有的卡片，含种子库权益 + 持卡实际信息。"""
    uc_result = await db.execute(
        select(UserCard)
        .where(UserCard.user_id == user_id)
        .order_by(UserCard.sort_order, UserCard.created_at)
    )
    user_cards = uc_result.scalars().all()
    if not user_cards:
        return []

    results = []
    for uc in user_cards:
        item = {
            "id": uc.id,
            "user_card_id": uc.id,
            "card_id": uc.card_id,
            "nickname": uc.nickname,
            "is_active": uc.is_active,
            "last_four": uc.last_four,
            "credit_limit": uc.credit_limit,
            "issue_date": uc.issue_date,
            "expire_date": uc.expire_date,
            "annual_fee_condition": uc.annual_fee_condition,
            "annual_fee_waived": uc.annual_fee_waived,
            "sort_order": uc.sort_order,
            "notes": uc.notes,
            "created_at": uc.created_at.isoformat() if uc.created_at else None,
            "updated_at": uc.updated_at.isoformat() if uc.updated_at else None,
        }

        # 如果关联了种子库卡片，附带权益信息
        if uc.card_id:
            card_result = await db.execute(
                select(CreditCard)
                .where(CreditCard.id == uc.card_id)
                .options(selectinload(CreditCard.benefits))
            )
            card = card_result.scalar_one_or_none()
            if card:
                item["card"] = {
                    "id": card.id,
                    "bank": card.bank,
                    "name": card.name,
                    "network": card.network,
                    "level": card.level,
                    "annual_fee": card.annual_fee,
                    "description": card.description,
                    "benefits": [
                        {
                            "id": b.id,
                            "title": b.title,
                            "description": b.description,
                            "benefit_type": b.benefit_type,
                            "category": b.category,
                            "value_text": b.value_text,
                            "discount_percent": b.discount_percent,
                            "points_per_yuan": b.points_per_yuan,
                            "cashback_percent": b.cashback_percent,
                            "usage_limit": b.usage_limit,
                        }
                        for b in card.benefits if b.is_active
                    ],
                    "redemptions": [],  # 按需加载
                }

        results.append(item)
    return results


async def add_user_card(db: AsyncSession, user_id: str, card_id: str, **kwargs) -> dict:
    """添加卡片到我的卡包。card_id 可为空（自定义卡）。"""
    # 检查是否已添加（同一 card_id 不重复）
    if card_id:
        existing = await db.execute(
            select(UserCard).where(
                UserCard.user_id == user_id,
                UserCard.card_id == card_id,
            )
        )
        if existing.scalar_one_or_none():
            return {"ok": False, "error": "该卡已添加"}

    uc = UserCard(
        id=str(uuid.uuid4()),
        user_id=user_id,
        card_id=card_id or "",
        nickname=kwargs.get("nickname"),
        last_four=kwargs.get("last_four"),
        credit_limit=kwargs.get("credit_limit"),
        issue_date=kwargs.get("issue_date"),
        expire_date=kwargs.get("expire_date"),
        annual_fee_condition=kwargs.get("annual_fee_condition"),
        annual_fee_waived=kwargs.get("annual_fee_waived"),
        notes=kwargs.get("notes"),
        sort_order=kwargs.get("sort_order", 0),
    )
    db.add(uc)
    await db.commit()
    return {"ok": True, "id": uc.id, "card_id": card_id}


async def update_user_card(db: AsyncSession, user_id: str, user_card_id: str, **kwargs) -> dict:
    """更新我的卡包中某张卡的信息。user_card_id 是 user_cards.id。"""
    result = await db.execute(
        select(UserCard).where(
            UserCard.id == user_card_id,
            UserCard.user_id == user_id,
        )
    )
    uc = result.scalar_one_or_none()
    if not uc:
        return {"ok": False, "error": "卡片不存在"}

    # 可更新字段
    updatable = [
        "nickname", "last_four", "credit_limit", "issue_date", "expire_date",
        "annual_fee_condition", "annual_fee_waived", "sort_order", "notes", "is_active",
    ]
    for field in updatable:
        if field in kwargs and kwargs[field] is not None:
            val = kwargs[field]
            if field == "last_four" and val:
                val = str(val)[:4]
            if field == "nickname" and val:
                val = str(val)[:128]
            setattr(uc, field, val)

    await db.commit()
    return {"ok": True, "id": uc.id}


async def remove_user_card(db: AsyncSession, user_id: str, user_card_id: str):
    """从卡包删除（物理删除）。"""
    await db.execute(
        delete(UserCard).where(
            UserCard.id == user_card_id,
            UserCard.user_id == user_id,
        )
    )
    await db.commit()


async def search_cards_for_add(db: AsyncSession, keyword: str = "", bank: str = "") -> list[dict]:
    """搜索种子库卡片，供添加时选择。"""
    query = select(CreditCard).where(CreditCard.is_active == True)
    if bank:
        query = query.where(CreditCard.bank == bank)
    if keyword:
        kw = f"%{keyword}%"
        query = query.where(
            or_(
                CreditCard.name.ilike(kw),
                CreditCard.bank.ilike(kw),
            )
        )
    query = query.order_by(CreditCard.bank, CreditCard.level)
    result = await db.execute(query)
    cards = result.scalars().all()
    return [
        {
            "id": c.id,
            "bank": c.bank,
            "name": c.name,
            "network": c.network,
            "level": c.level,
            "annual_fee": c.annual_fee,
        }
        for c in cards
    ]


async def list_banks(db: AsyncSession) -> list[str]:
    """返回种子库中所有银行名。"""
    result = await db.execute(
        select(CreditCard.bank)
        .where(CreditCard.is_active == True)
        .distinct()
        .order_by(CreditCard.bank)
    )
    return [r[0] for r in result.all()]


# --- 收藏 ---

async def list_favorites(
    db: AsyncSession, user_id: str, target_type: str,
    page: int = 1, page_size: int = 20,
) -> dict:
    query = (
        select(UserFavorite)
        .where(
            UserFavorite.user_id == user_id,
            UserFavorite.target_type == target_type,
        )
        .order_by(desc(UserFavorite.created_at))
    )
    count_query = (
        select(func.count(UserFavorite.id))
        .where(
            UserFavorite.user_id == user_id,
            UserFavorite.target_type == target_type,
        )
    )
    total = (await db.execute(count_query)).scalar() or 0
    total_pages = max(1, ceil(total / page_size))
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = [
        {
            "id": f.id,
            "target_id": f.target_id,
            "target_type": f.target_type,
            "target_title": f.target_title,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in result.scalars().all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


async def add_favorite(
    db: AsyncSession, user_id: str, target_id: str, target_type: str, target_title: str
) -> dict:
    existing = await db.execute(
        select(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.target_id == target_id,
            UserFavorite.target_type == target_type,
        )
    )
    if existing.scalar_one_or_none():
        return {"ok": True, "message": "已收藏"}
    f = UserFavorite(
        id=str(uuid.uuid4()),
        user_id=user_id,
        target_id=target_id,
        target_type=target_type,
        target_title=target_title,
    )
    db.add(f)
    await db.commit()
    return {"ok": True, "id": f.id, "target_id": target_id}


async def remove_favorite(db: AsyncSession, user_id: str, target_id: str, target_type: str):
    await db.execute(
        delete(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.target_id == target_id,
            UserFavorite.target_type == target_type,
        )
    )
    await db.commit()


# --- 搜索历史 ---

async def add_search_history(db: AsyncSession, user_id: str, keyword: str, result_count: int = 0) -> dict:
    existing_result = await db.execute(
        select(UserSearchHistory).where(
            UserSearchHistory.user_id == user_id,
            UserSearchHistory.keyword == keyword,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        existing.created_at = datetime.now()
        existing.result_count = result_count
        await db.commit()
        return {"ok": True, "id": existing.id}

    h = UserSearchHistory(
        id=str(uuid.uuid4()),
        user_id=user_id,
        keyword=keyword,
        result_count=result_count,
    )
    db.add(h)
    await db.commit()
    total = (await db.execute(
        select(func.count(UserSearchHistory.id)).where(UserSearchHistory.user_id == user_id)
    )).scalar() or 0
    if total > 100:
        last_valid = (
            await db.execute(
                select(UserSearchHistory)
                .where(UserSearchHistory.user_id == user_id)
                .order_by(desc(UserSearchHistory.created_at))
                .offset(99)
                .limit(1)
            )
        ).scalar_one_or_none()
        if last_valid:
            await db.execute(
                delete(UserSearchHistory).where(
                    UserSearchHistory.user_id == user_id,
                    UserSearchHistory.created_at < last_valid.created_at,
                )
            )
            await db.commit()
    return {"ok": True, "id": h.id}


async def list_search_history(db: AsyncSession, user_id: str, limit: int = 20) -> list[dict]:
    subq = (
        select(
            UserSearchHistory.keyword,
            func.max(UserSearchHistory.created_at).label("max_at"),
            func.max(UserSearchHistory.result_count).label("max_result"),
        )
        .where(UserSearchHistory.user_id == user_id)
        .group_by(UserSearchHistory.keyword)
        .order_by(func.max(UserSearchHistory.created_at).desc())
        .limit(limit)
        .subquery()
    )
    result = await db.execute(select(subq))
    return [
        {"keyword": row.keyword, "result_count": row.max_result, "last_searched": row.max_at.isoformat()}
        for row in result.all()
    ]


async def clear_search_history(db: AsyncSession, user_id: str):
    await db.execute(delete(UserSearchHistory).where(UserSearchHistory.user_id == user_id))
    await db.commit()
