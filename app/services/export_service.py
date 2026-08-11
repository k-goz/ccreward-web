"""数据导出服务 — JSON & CSV 导出用户全部数据。"""

import csv
import io
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserCard
from app.models.card import CreditCard
from app.models.benefit import CardBenefit
from app.models.benefit_usage import BenefitUsageTrack
from app.models.custom_benefit import UserBenefitOverride, UserRedemptionOverride
from app.models.redemption import RedemptionItem
from app.services.custom_benefit_service import merge_benefits, get_card_redemptions_full


def _round2(val: float | None) -> float | None:
    if val is None:
        return None
    return round(val, 2)


def _serialize_date(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime,)):
        return val.isoformat()
    return str(val)


# ──────────────────────────────────────────────
# JSON 导出
# ──────────────────────────────────────────────

async def export_user_data(user_id: str, db: AsyncSession, format: str = "json") -> dict:
    """导出用户所有数据（卡包/权益/账单/消费）为 dict。"""
    # 用户卡片
    uc_result = await db.execute(
        select(UserCard).where(UserCard.user_id == user_id).order_by(UserCard.sort_order, UserCard.created_at)
    )
    user_cards = uc_result.scalars().all()

    cards_export = []
    all_benefit_overrides = []
    all_redemption_overrides = []
    all_usage_tracks = []

    for uc in user_cards:
        # 卡片基本信息
        card_info = {
            "id": uc.id,
            "user_card_id": uc.id,
            "card_id": uc.card_id,
            "nickname": uc.nickname,
            "is_active": uc.is_active,
            "last_four": uc.last_four,
            "credit_limit": _round2(uc.credit_limit),
            "issue_date": uc.issue_date,
            "expire_date": uc.expire_date,
            "annual_fee_condition": uc.annual_fee_condition,
            "annual_fee_waived": uc.annual_fee_waived,
            "sort_order": uc.sort_order,
            "notes": uc.notes,
            "created_at": _serialize_date(uc.created_at),
            "updated_at": _serialize_date(uc.updated_at),
        }

        # 种子库卡片信息
        seed_card = None
        if uc.card_id:
            c_result = await db.execute(
                select(CreditCard).where(CreditCard.id == uc.card_id)
            )
            c = c_result.scalar_one_or_none()
            if c:
                seed_card = {
                    "id": c.id,
                    "bank": c.bank,
                    "name": c.name,
                    "network": c.network.value if hasattr(c.network, "value") else str(c.network),
                    "level": c.level.value if hasattr(c.level, "value") else str(c.level),
                    "annual_fee": c.annual_fee,
                    "description": c.description,
                }
        card_info["card"] = seed_card

        # 合并权益
        benefits = await merge_benefits(uc.id, db)
        card_info["benefits"] = benefits

        # 积分兑换
        if uc.card_id:
            redemptions = await get_card_redemptions_full(uc.card_id, user_id, db)
            card_info["redemptions"] = redemptions
        else:
            card_info["redemptions"] = []

        cards_export.append(card_info)

    # 权益覆盖记录
    ovr_result = await db.execute(
        select(UserBenefitOverride).where(UserBenefitOverride.user_id == user_id)
    )
    for ovr in ovr_result.scalars().all():
        all_benefit_overrides.append({
            "id": ovr.id,
            "user_card_id": ovr.user_card_id,
            "card_id": ovr.card_id,
            "benefit_id": ovr.benefit_id,
            "title": ovr.title,
            "description": ovr.description,
            "benefit_type": ovr.benefit_type,
            "category": ovr.category,
            "discount_percent": _round2(ovr.discount_percent),
            "cashback_percent": _round2(ovr.cashback_percent),
            "points_per_yuan": _round2(ovr.points_per_yuan),
            "value_text": ovr.value_text,
            "usage_limit": ovr.usage_limit,
            "merchant_tags": ovr.merchant_tags,
            "is_active": ovr.is_active,
            "effective_from": _serialize_date(ovr.effective_from),
            "effective_to": _serialize_date(ovr.effective_to),
            "notes": ovr.notes,
            "created_at": _serialize_date(ovr.created_at),
            "updated_at": _serialize_date(ovr.updated_at),
        })

    # 自定义兑换项
    red_result = await db.execute(
        select(UserRedemptionOverride).where(UserRedemptionOverride.user_id == user_id)
    )
    for r in red_result.scalars().all():
        all_redemption_overrides.append({
            "id": r.id,
            "user_card_id": r.user_card_id,
            "card_id": r.card_id,
            "item_name": r.item_name,
            "merchant_name": r.merchant_name,
            "category": r.category,
            "points_required": _round2(r.points_required),
            "cash_value": _round2(r.cash_value),
            "description": r.description,
            "is_active": r.is_active,
            "notes": r.notes,
            "created_at": _serialize_date(r.created_at),
            "updated_at": _serialize_date(r.updated_at),
        })

    # 权益使用记录
    usage_result = await db.execute(
        select(BenefitUsageTrack).where(BenefitUsageTrack.user_id == user_id)
    )
    for t in usage_result.scalars().all():
        all_usage_tracks.append({
            "id": t.id,
            "user_card_id": t.user_card_id,
            "benefit_id": t.benefit_id,
            "benefit_title": t.benefit_title,
            "monthly_limit": t.monthly_limit,
            "used_this_month": t.used_this_month,
            "last_used_date": _serialize_date(t.last_used_date),
            "last_reset_month": t.last_reset_month,
            "year_limit": t.year_limit,
            "used_this_year": t.used_this_year,
            "total_used": t.total_used,
            "is_active": t.is_active,
            "created_at": _serialize_date(t.created_at),
            "updated_at": _serialize_date(t.updated_at),
        })

    result = {
        "exported_at": datetime.now().isoformat(),
        "user_id": user_id,
        "format": format,
        "cards": cards_export,
        "benefit_overrides": all_benefit_overrides,
        "redemption_overrides": all_redemption_overrides,
        "usage_tracks": all_usage_tracks,
    }
    return result


# ──────────────────────────────────────────────
# CSV 导出
# ──────────────────────────────────────────────

async def export_csv(user_id: str, db: AsyncSession) -> dict:
    """导出为 CSV，返回 cards.csv 和 expenses.csv 两个文件的文本内容。"""
    data = await export_user_data(user_id, db)

    # cards.csv: 卡片信息 + 权益数量
    cards_output = io.StringIO()
    cards_writer = csv.writer(cards_output)
    cards_writer.writerow([
        "user_card_id", "bank", "card_name", "nickname", "network", "level",
        "annual_fee", "credit_limit", "last_four", "issue_date", "expire_date",
        "annual_fee_waived", "benefit_count", "redemption_count", "is_active",
        "notes",
    ])
    for c in data["cards"]:
        seed = c.get("card") or {}
        cards_writer.writerow([
            c["user_card_id"],
            seed.get("bank", ""),
            seed.get("name", ""),
            c.get("nickname", ""),
            seed.get("network", ""),
            seed.get("level", ""),
            seed.get("annual_fee", ""),
            c.get("credit_limit", ""),
            c.get("last_four", ""),
            c.get("issue_date", ""),
            c.get("expire_date", ""),
            "是" if c.get("annual_fee_waived") else "否",
            len(c.get("benefits", [])),
            len(c.get("redemptions", [])),
            "是" if c.get("is_active") else "否",
            c.get("notes", ""),
        ])

    # expenses.csv: 权益使用进度
    expenses_output = io.StringIO()
    expenses_writer = csv.writer(expenses_output)
    expenses_writer.writerow([
        "user_card_id", "benefit_id", "benefit_title",
        "used_this_month", "monthly_limit", "used_this_year", "year_limit",
        "total_used", "last_used_date",
    ])
    for t in data["usage_tracks"]:
        expenses_writer.writerow([
            t["user_card_id"],
            t["benefit_id"],
            t["benefit_title"],
            t["used_this_month"],
            t["monthly_limit"] or "",
            t["used_this_year"],
            t["year_limit"] or "",
            t["total_used"],
            t["last_used_date"] or "",
        ])

    # UTF-8 BOM for Chinese compatibility
    cards_bom = "\ufeff" + cards_output.getvalue()
    expenses_bom = "\ufeff" + expenses_output.getvalue()

    return {
        "cards.csv": cards_bom,
        "expenses.csv": expenses_bom,
    }
