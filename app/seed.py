"""种子数据导入：支持首次全量导入与增量更新（upsert）。

数据来源：各行官网/掌上生活/发现精彩等App公开权益信息，人工整理。
后续可由爬虫自动更新或众包维护。
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, init_db
from app.models.card import CreditCard
from app.models.benefit import CardBenefit
from app.models.activity import MerchantActivity
from app.models.redemption import RedemptionItem
from app.models.user import UserCard
from app.models.bank_offer import BankOffer
from app.seed_data.cards import CARDS, BENEFITS
from app.seed_data.activities import ACTIVITIES
from app.seed_data.redemptions import REDEMPTIONS
from app.seed_data.bank_offers import BANK_OFFERS

from app.models.benefit_usage import BenefitUsageTrack
import uuid

logger = logging.getLogger(__name__)


async def _upsert(db: AsyncSession, model, items: list[dict], label: str) -> int:
    count = 0
    for data in items:
        pk = data["id"]
        existing = await db.get(model, pk)
        if existing:
            for key, value in data.items():
                setattr(existing, key, value)
        else:
            db.add(model(**data))
        count += 1
    await db.commit()
    logger.info(f"[{label}] 处理 {count} 条")
    return count


async def seed_database(db: AsyncSession, force: bool = False) -> dict:
    if not force:
        result = await db.execute(select(CreditCard).limit(1))
        if result.scalar_one_or_none():
            existing_cards = (await db.execute(select(CreditCard))).scalars().all()
            existing_acts = (await db.execute(select(MerchantActivity))).scalars().all()
            logger.info(
                f"数据库已有数据（{len(existing_cards)}卡/{len(existing_acts)}活动），执行增量更新"
            )

    stats = {
        "cards": await _upsert(db, CreditCard, CARDS, "cards"),
        "benefits": await _upsert(db, CardBenefit, BENEFITS, "benefits"),
        "activities": await _upsert(db, MerchantActivity, ACTIVITIES, "activities"),
        "redemptions": await _upsert(db, RedemptionItem, REDEMPTIONS, "redemptions"),
        "bank_offers": await _upsert(db, BankOffer, BANK_OFFERS, "bank_offers"),
    }
    logger.info(
        f"种子数据同步完成: {stats['cards']}张卡, {stats['benefits']}条权益, "
        f"{stats['activities']}条活动, {stats['redemptions']}条兑换商品"
    )
    await seed_benefit_usage(db)
    return stats


async def seed_benefit_usage(db: AsyncSession) -> None:
    """种子数据：为已有 user_cards 建立默认的 usage track。"""
    result = await db.execute(select(UserCard).where(UserCard.is_active == True).limit(50))
    user_cards = result.scalars().all()
    if not user_cards:
        logger.info("[benefit_usage] 无用户卡，跳过种子数据")
        return

    added = 0
    for uc in user_cards:
        if not uc.card_id:
            continue
        benefits = (
            await db.execute(select(CardBenefit).where(CardBenefit.card_id == uc.card_id, CardBenefit.is_active == True))
        ).scalars().all()
        for b in benefits:
            existing = await db.execute(
                select(BenefitUsageTrack).where(
                    BenefitUsageTrack.user_id == uc.user_id,
                    BenefitUsageTrack.benefit_id == b.id,
                )
            )
            if existing.scalar_one_or_none():
                continue
            track = BenefitUsageTrack(
                id=str(uuid.uuid4()),
                user_id=uc.user_id,
                user_card_id=uc.id,
                benefit_id=b.id,
                benefit_title=b.title,
                monthly_limit=None,
                used_this_month=0,
                year_limit=None,
                used_this_year=0,
                total_used=0,
                last_reset_month=None,
            )
            db.add(track)
            added += 1

    if added:
        await db.commit()
    logger.info(f"[benefit_usage] 种子数据 {added} 条")


async def run_seed() -> None:
    await init_db()
    async with async_session() as db:
        await seed_database(db)
