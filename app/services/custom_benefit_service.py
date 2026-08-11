"""自定义权益服务层 — 合并种子权益与用户覆盖。"""

import uuid
from datetime import date

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.benefit import CardBenefit
from app.models.card import CreditCard
from app.models.user import UserCard
from app.models.redemption import RedemptionItem
from app.models.custom_benefit import UserBenefitOverride, UserRedemptionOverride


# ──────────────────────────────────────────────
# 权益覆盖
# ──────────────────────────────────────────────

async def merge_benefits(user_card_id: str, db: AsyncSession) -> list[dict]:
    """合并种子权益 + 用户覆盖，用户覆盖优先。

    流程：
    1. 查 user_card → 拿到 card_id
    2. 查 card_benefits（种子权益）
    3. 查 user_benefit_overrides（覆盖/新增）
    4. 以 benefit_id 为 key 合并：覆盖字段替换种子字段
       benefit_id 为空的是新增额外权益
    5. 返回完整列表
    """
    # 1. 拿到用户卡
    uc_result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id)
    )
    uc = uc_result.scalar_one_or_none()
    if not uc:
        return []

    card_id = uc.card_id

    # 2. 种子权益
    seed_benefits: dict[str, dict] = {}
    if card_id:
        b_result = await db.execute(
            select(CardBenefit).where(
                CardBenefit.card_id == card_id,
                CardBenefit.is_active == True,
            )
        )
        for b in b_result.scalars().all():
            seed_benefits[b.id] = {
                "id": b.id,
                "card_id": b.card_id,
                "title": b.title,
                "description": b.description,
                "benefit_type": b.benefit_type.value if hasattr(b.benefit_type, "value") else str(b.benefit_type),
                "category": b.category.value if hasattr(b.category, "value") else str(b.category),
                "discount_percent": b.discount_percent,
                "cashback_percent": b.cashback_percent,
                "points_per_yuan": b.points_per_yuan,
                "value_text": b.value_text,
                "usage_limit": b.usage_limit,
                "merchant_tags": b.merchant_tags,
                "is_active": b.is_active,
                "source": "seed",  # 标记来源
                "override_id": None,
            }

    # 3. 用户覆盖
    ovr_result = await db.execute(
        select(UserBenefitOverride).where(
            UserBenefitOverride.user_card_id == user_card_id,
            UserBenefitOverride.is_active == True,
        )
    )
    overrides = ovr_result.scalars().all()

    # 4. 合并
    extra_benefits: list[dict] = []
    today = date.today()

    for ovr in overrides:
        # 检查有效期
        if ovr.effective_from and ovr.effective_from > today:
            continue
        if ovr.effective_to and ovr.effective_to < today:
            continue

        if ovr.benefit_id and ovr.benefit_id in seed_benefits:
            # 覆盖已有种子权益
            base = seed_benefits[ovr.benefit_id]
            _apply_overrides(base, ovr)
            base["source"] = "overridden"
            base["override_id"] = ovr.id
        else:
            # 新增额外权益
            extra = {
                "id": ovr.id,
                "card_id": ovr.card_id or card_id,
                "title": ovr.title or "",
                "description": ovr.description or "",
                "benefit_type": ovr.benefit_type or "其他",
                "category": ovr.category or "通用",
                "discount_percent": ovr.discount_percent,
                "cashback_percent": ovr.cashback_percent,
                "points_per_yuan": ovr.points_per_yuan,
                "value_text": ovr.value_text,
                "usage_limit": ovr.usage_limit,
                "merchant_tags": ovr.merchant_tags,
                "is_active": True,
                "source": "custom",
                "override_id": ovr.id,
            }
            extra_benefits.append(extra)

    result = list(seed_benefits.values()) + extra_benefits
    return result


def _apply_overrides(base: dict, ovr: UserBenefitOverride) -> None:
    """将覆盖对象中非 None 的字段应用到 base dict 上。"""
    overridable = [
        "title", "description", "benefit_type", "category",
        "discount_percent", "cashback_percent", "points_per_yuan",
        "value_text", "usage_limit", "merchant_tags",
    ]
    for field in overridable:
        val = getattr(ovr, field, None)
        if val is not None:
            base[field] = val


async def upsert_benefit_override(data: dict, user_id: str, db: AsyncSession) -> dict:
    """创建或更新权益覆盖。

    data 必须包含 user_card_id + card_id。
    如果提供了 benefit_id 且已存在覆盖则更新，否则创建。
    """
    user_card_id = data.get("user_card_id")
    benefit_id = data.get("benefit_id")

    if benefit_id:
        # 查找已有覆盖
        existing = await db.execute(
            select(UserBenefitOverride).where(
                UserBenefitOverride.user_card_id == user_card_id,
                UserBenefitOverride.benefit_id == benefit_id,
            )
        )
        existing = existing.scalar_one_or_none()
        if existing:
            # 更新
            return await _update_override(existing, data, db)

    # 新建
    ovr = UserBenefitOverride(
        user_id=user_id,
        user_card_id=user_card_id,
        card_id=data.get("card_id"),
        benefit_id=benefit_id,
        title=data.get("title"),
        description=data.get("description"),
        benefit_type=data.get("benefit_type"),
        category=data.get("category"),
        discount_percent=data.get("discount_percent"),
        cashback_percent=data.get("cashback_percent"),
        points_per_yuan=data.get("points_per_yuan"),
        value_text=data.get("value_text"),
        usage_limit=data.get("usage_limit"),
        merchant_tags=data.get("merchant_tags"),
        effective_from=data.get("effective_from"),
        effective_to=data.get("effective_to"),
        notes=data.get("notes"),
    )
    db.add(ovr)
    await db.commit()
    await db.refresh(ovr)
    return {"ok": True, "id": ovr.id, "benefit_id": benefit_id}


async def _update_override(ovr: UserBenefitOverride, data: dict, db: AsyncSession) -> dict:
    updatable = [
        "title", "description", "benefit_type", "category",
        "discount_percent", "cashback_percent", "points_per_yuan",
        "value_text", "usage_limit", "merchant_tags",
        "is_active", "effective_from", "effective_to", "notes",
    ]
    for field in updatable:
        if field in data and data[field] is not None:
            setattr(ovr, field, data[field])
    await db.commit()
    return {"ok": True, "id": ovr.id, "benefit_id": ovr.benefit_id, "updated": True}


async def delete_benefit_override(override_id: str, db: AsyncSession) -> dict:
    """删除权益覆盖（物理删除）。"""
    result = await db.execute(
        select(UserBenefitOverride).where(UserBenefitOverride.id == override_id)
    )
    ovr = result.scalar_one_or_none()
    if not ovr:
        return {"ok": False, "error": "覆盖不存在"}
    await db.delete(ovr)
    await db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# 自定义兑换项
# ──────────────────────────────────────────────

async def add_redemption(data: dict, user_id: str, db: AsyncSession) -> dict:
    """添加自定义积分兑换项。"""
    r = UserRedemptionOverride(
        user_id=user_id,
        user_card_id=data["user_card_id"],
        card_id=data.get("card_id"),
        item_name=data["item_name"],
        merchant_name=data.get("merchant_name"),
        category=data.get("category"),
        points_required=data["points_required"],
        cash_value=data.get("cash_value"),
        description=data.get("description"),
        notes=data.get("notes"),
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return {"ok": True, "id": r.id, "item_name": r.item_name}


async def get_card_redemptions_full(card_id: str, user_id: str, db: AsyncSession) -> list[dict]:
    """种子兑换 + 用户自定义兑换。"""
    # 种子兑换
    seed_result = await db.execute(
        select(RedemptionItem).where(
            RedemptionItem.card_id == card_id,
            RedemptionItem.is_active == True,
        )
    )
    items = []
    for s in seed_result.scalars().all():
        items.append({
            "id": s.id,
            "card_id": s.card_id,
            "item_name": s.item_name,
            "merchant_name": s.merchant_name,
            "category": s.category,
            "points_required": s.points_required,
            "cash_value": _round2(s.cash_value),
            "description": s.description,
            "source": "seed",
        })

    # 用户自定义兑换
    user_result = await db.execute(
        select(UserRedemptionOverride).where(
            UserRedemptionOverride.user_id == user_id,
            UserRedemptionOverride.card_id == card_id,
            UserRedemptionOverride.is_active == True,
        )
    )
    for u in user_result.scalars().all():
        items.append({
            "id": u.id,
            "card_id": u.card_id,
            "item_name": u.item_name,
            "merchant_name": u.merchant_name,
            "category": u.category,
            "points_required": u.points_required,
            "cash_value": _round2(u.cash_value),
            "description": u.description,
            "source": "custom",
        })

    return items


async def delete_redemption_override(override_id: str, db: AsyncSession) -> dict:
    """删除自定义兑换项（物理删除）。"""
    result = await db.execute(
        select(UserRedemptionOverride).where(UserRedemptionOverride.id == override_id)
    )
    r = result.scalar_one_or_none()
    if not r:
        return {"ok": False, "error": "兑换项不存在"}
    await db.delete(r)
    await db.commit()
    return {"ok": True}


def _round2(val: float | None) -> float | None:
    if val is None:
        return None
    return round(val, 2)
