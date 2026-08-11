"""信用卡服务层。"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.card import CreditCard
from app.models.benefit import CardBenefit
from app.models.redemption import RedemptionItem
from app.models.user import UserCard
from app.schemas.card import CardWithBenefits
from app.schemas.redemption import RedemptionOut


async def list_cards(
    db: AsyncSession,
    bank: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """分页查询信用卡列表。"""
    base_stmt = select(CreditCard).where(CreditCard.is_active == True).options(selectinload(CreditCard.benefits))
    count_stmt = select(func.count(CreditCard.id)).where(CreditCard.is_active == True)

    if bank:
        base_stmt = base_stmt.where(CreditCard.bank == bank)
        count_stmt = count_stmt.where(CreditCard.bank == bank)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    base_stmt = base_stmt.order_by(CreditCard.bank, CreditCard.name)
    base_stmt = base_stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(base_stmt)
    cards = result.scalars().unique().all()

    return {
        "items": [CardWithBenefits.model_validate(c) for c in cards],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


async def get_card(db: AsyncSession, card_id: str) -> CardWithBenefits | None:
    stmt = (
        select(CreditCard)
        .where(CreditCard.id == card_id)
        .options(selectinload(CreditCard.benefits))
    )
    result = await db.execute(stmt)
    card = result.scalar_one_or_none()
    if not card:
        return None
    return CardWithBenefits.model_validate(card)


async def get_user_cards(db: AsyncSession, user_id: str) -> list[CardWithBenefits]:
    uc_stmt = select(UserCard.card_id).where(UserCard.user_id == user_id, UserCard.is_active == True)
    uc_result = await db.execute(uc_stmt)
    card_ids = [row[0] for row in uc_result.all()]
    if not card_ids:
        return []
    stmt = (
        select(CreditCard)
        .where(CreditCard.id.in_(card_ids), CreditCard.is_active == True)
        .options(selectinload(CreditCard.benefits))
    )
    result = await db.execute(stmt)
    cards = result.scalars().unique().all()
    return [CardWithBenefits.model_validate(c) for c in cards]


async def add_user_card(db: AsyncSession, user_id: str, card_id: str, nickname: str | None = None) -> UserCard:
    import uuid
    user_card = UserCard(id=str(uuid.uuid4()), user_id=user_id, card_id=card_id, nickname=nickname)
    db.add(user_card)
    await db.commit()
    await db.refresh(user_card)
    return user_card


async def get_card_redemptions(db: AsyncSession, card_id: str | None = None) -> list[RedemptionOut]:
    stmt = select(RedemptionItem).where(RedemptionItem.is_active == True)
    if card_id:
        stmt = stmt.where(RedemptionItem.card_id == card_id)
    result = await db.execute(stmt)
    return [RedemptionOut.model_validate(r) for r in result.scalars().all()]


async def get_stats(db: AsyncSession) -> dict:
    """信用卡与权益统计概览。"""
    card_count = (await db.execute(select(func.count(CreditCard.id)).where(CreditCard.is_active == True))).scalar() or 0
    benefit_count = (await db.execute(select(func.count(CardBenefit.id)).where(CardBenefit.is_active == True))).scalar() or 0
    redemption_count = (await db.execute(select(func.count(RedemptionItem.id)).where(RedemptionItem.is_active == True))).scalar() or 0

    # 银行分布
    bank_result = await db.execute(
        select(CreditCard.bank, func.count(CreditCard.id))
        .where(CreditCard.is_active == True)
        .group_by(CreditCard.bank)
        .order_by(func.count(CreditCard.id).desc())
    )
    banks = {row.bank: row[1] for row in bank_result.all()}

    # 卡等级分布
    level_result = await db.execute(
        select(CreditCard.level, func.count(CreditCard.id))
        .where(CreditCard.is_active == True)
        .group_by(CreditCard.level)
    )
    levels = {row.level.value if hasattr(row.level, "value") else str(row.level): row[1] for row in level_result.all()}

    # 权益类型分布
    type_result = await db.execute(
        select(CardBenefit.benefit_type, func.count(CardBenefit.id))
        .where(CardBenefit.is_active == True)
        .group_by(CardBenefit.benefit_type)
        .order_by(func.count(CardBenefit.id).desc())
    )
    benefit_types = {row.benefit_type.value if hasattr(row.benefit_type, "value") else str(row.benefit_type): row[1] for row in type_result.all()}

    return {
        "cards": card_count,
        "banks": len(banks),
        "benefits": benefit_count,
        "redemptions": redemption_count,
        "by_bank": banks,
        "by_level": levels,
        "by_benefit_type": benefit_types,
    }
