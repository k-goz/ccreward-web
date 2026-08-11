"""消费画像 API — 聚合分析消费数据，提供品类分布、趋势、返现估算。"""

import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.bill import BillRecord, ExpenseRecord
from app.models.card import CreditCard
from app.models.benefit import CardBenefit, BenefitType, BenefitCategory
from app.models.user import UserCard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spending", tags=["消费画像"])

# ── 品类映射：消费类别 → 权益类别 ──
CATEGORY_TO_BENEFIT = {
    "餐饮": ["餐饮美食", "咖啡茶饮"],
    "购物": ["购物消费", "线上消费", "超市便利"],
    "出行": ["出行旅游", "加油"],
    "娱乐": ["休闲娱乐"],
    "生活": ["生活缴费", "通用"],
    "其他": ["通用"],
}


async def _get_user_cards(user_id: str, db: AsyncSession) -> list[dict]:
    """获取用户所有卡片（含权益）。"""
    result = await db.execute(
        select(UserCard).where(UserCard.user_id == user_id, UserCard.is_active == True)
    )
    user_cards = result.scalars().all()
    return [{"user_card": uc, "card_id": uc.card_id} for uc in user_cards]


@router.get("/summary", summary="月度消费总览")
async def spending_summary(
    year: int = Query(description="年"),
    month: int = Query(description="月", ge=1, le=12),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """返回本月总消费、环比变化、品类分布、日均消费。"""
    user_id = user["user_id"]

    # 本月消费（不含退款）
    stmt = select(func.coalesce(func.sum(ExpenseRecord.amount), 0.0)).where(
        ExpenseRecord.user_id == user_id,
        ExpenseRecord.is_refund == False,
        extract("year", ExpenseRecord.expense_date) == year,
        extract("month", ExpenseRecord.expense_date) == month,
    )
    total = (await db.execute(stmt)).scalar() or 0.0

    # 上月消费
    prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    prev_stmt = select(func.coalesce(func.sum(ExpenseRecord.amount), 0.0)).where(
        ExpenseRecord.user_id == user_id,
        ExpenseRecord.is_refund == False,
        extract("year", ExpenseRecord.expense_date) == prev_year,
        extract("month", ExpenseRecord.expense_date) == prev_month,
    )
    prev_total = (await db.execute(prev_stmt)).scalar() or 0.0

    # 环比变化
    mom_change = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0.0

    # 品类分布
    cat_stmt = (
        select(ExpenseRecord.category, func.coalesce(func.sum(ExpenseRecord.amount), 0.0))
        .where(
            ExpenseRecord.user_id == user_id,
            ExpenseRecord.is_refund == False,
            extract("year", ExpenseRecord.expense_date) == year,
            extract("month", ExpenseRecord.expense_date) == month,
        )
        .group_by(ExpenseRecord.category)
    )
    cat_rows = (await db.execute(cat_stmt)).all()
    categories = [
        {"category": row[0], "amount": round(row[1], 2),
         "percent": round(row[1] / total * 100, 1) if total > 0 else 0}
        for row in cat_rows
    ]
    categories.sort(key=lambda x: x["amount"], reverse=True)

    # 日均消费
    days_in_month = monthrange(year, month)[1]
    today = date.today()
    elapsed_days = min(today.day, days_in_month) if today.year == year and today.month == month else days_in_month
    daily_avg = round(total / elapsed_days, 2) if elapsed_days > 0 else 0.0

    # 最大单笔
    max_stmt = select(func.coalesce(func.max(ExpenseRecord.amount), 0.0)).where(
        ExpenseRecord.user_id == user_id,
        ExpenseRecord.is_refund == False,
        extract("year", ExpenseRecord.expense_date) == year,
        extract("month", ExpenseRecord.expense_date) == month,
    )
    max_single = (await db.execute(max_stmt)).scalar() or 0.0

    # 品类数 & 交易笔数
    count_stmt = select(func.count(ExpenseRecord.id)).where(
        ExpenseRecord.user_id == user_id,
        ExpenseRecord.is_refund == False,
        extract("year", ExpenseRecord.expense_date) == year,
        extract("month", ExpenseRecord.expense_date) == month,
    )
    tx_count = (await db.execute(count_stmt)).scalar() or 0

    return {
        "year": year,
        "month": month,
        "total": round(total, 2),
        "prev_month_total": round(prev_total, 2),
        "mom_change_pct": round(mom_change, 1),
        "daily_avg": daily_avg,
        "max_single": round(max_single, 2),
        "category_count": len(categories),
        "tx_count": tx_count,
        "categories": categories,
    }


@router.get("/categories", summary="品类消费明细")
async def spending_categories(
    year: int = Query(description="年"),
    month: int = Query(description="月", ge=1, le=12),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回各品类总消费和笔数。"""
    user_id = user["user_id"]

    stmt = (
        select(
            ExpenseRecord.category,
            func.coalesce(func.sum(ExpenseRecord.amount), 0.0),
            func.count(ExpenseRecord.id),
        )
        .where(
            ExpenseRecord.user_id == user_id,
            ExpenseRecord.is_refund == False,
            extract("year", ExpenseRecord.expense_date) == year,
            extract("month", ExpenseRecord.expense_date) == month,
        )
        .group_by(ExpenseRecord.category)
        .order_by(func.sum(ExpenseRecord.amount).desc())
    )
    rows = (await db.execute(stmt)).all()
    total = sum(r[1] for r in rows) or 1.0
    return [
        {
            "category": row[0],
            "total_amount": round(row[1], 2),
            "count": row[2],
            "percent": round(row[1] / total * 100, 1),
        }
        for row in rows
    ]


@router.get("/trend", summary="近 N 月消费趋势")
async def spending_trend(
    months: int = Query(6, ge=1, le=24, description="最近 N 个月"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """每月总消费趋势（不含退款）。"""
    user_id = user["user_id"]

    today = date.today()
    results = []
    for i in range(months - 1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        stmt = select(func.coalesce(func.sum(ExpenseRecord.amount), 0.0)).where(
            ExpenseRecord.user_id == user_id,
            ExpenseRecord.is_refund == False,
            extract("year", ExpenseRecord.expense_date) == y,
            extract("month", ExpenseRecord.expense_date) == m,
        )
        total = (await db.execute(stmt)).scalar() or 0.0
        label = f"{m}月"
        results.append({"year": y, "month": m, "label": label, "total": round(total, 2)})
    return results


@router.get("/merchants", summary="Top 商户排行")
async def spending_merchants(
    year: int = Query(description="年"),
    month: int = Query(description="月", ge=1, le=12),
    limit: int = Query(10, ge=1, le=50, description="返回条数"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """按月查询 Top 商户消费排行。"""
    user_id = user["user_id"]

    stmt = (
        select(
            ExpenseRecord.merchant,
            func.coalesce(func.sum(ExpenseRecord.amount), 0.0),
            func.count(ExpenseRecord.id),
        )
        .where(
            ExpenseRecord.user_id == user_id,
            ExpenseRecord.is_refund == False,
            extract("year", ExpenseRecord.expense_date) == year,
            extract("month", ExpenseRecord.expense_date) == month,
            ExpenseRecord.merchant.isnot(None),
            ExpenseRecord.merchant != "",
        )
        .group_by(ExpenseRecord.merchant)
        .order_by(func.sum(ExpenseRecord.amount).desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    total = sum(r[1] for r in rows) or 1.0
    return [
        {
            "merchant": row[0] or "未知",
            "total_amount": round(row[1], 2),
            "count": row[2],
            "percent": round(row[1] / total * 100, 1),
        }
        for row in rows
    ]


@router.get("/credit-utilization", summary="卡片额度使用率")
async def credit_utilization(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """每张卡最近的额度使用率。"""
    user_id = user["user_id"]

    # 获取用户所有活跃卡
    uc_result = await db.execute(
        select(UserCard).where(UserCard.user_id == user_id, UserCard.is_active == True)
    )
    user_cards = uc_result.scalars().all()

    results = []
    for uc in user_cards:
        # 该卡最近一条账单记录
        br_stmt = (
            select(BillRecord)
            .where(BillRecord.user_card_id == uc.id, BillRecord.user_id == user_id)
            .order_by(BillRecord.created_at.desc())
            .limit(1)
        )
        br = (await db.execute(br_stmt)).scalar()

        # 查卡片信息
        card_info = None
        if uc.card_id:
            card_result = await db.execute(
                select(CreditCard).where(CreditCard.id == uc.card_id)
            )
            card_info = card_result.scalar()

        bank = card_info.bank if card_info else "自定义"
        card_name = uc.nickname or (card_info.name if card_info else "未知")

        usage_rate = br.usage_rate if br else 0.0
        credit_limit = br.credit_limit if br and br.credit_limit else (uc.credit_limit or 0.0)
        current_balance = br.current_balance if br else 0.0

        # 颜色警告
        if usage_rate >= 80:
            level = "danger"
        elif usage_rate >= 50:
            level = "warning"
        else:
            level = "safe"

        results.append({
            "user_card_id": uc.id,
            "bank": bank,
            "card_name": card_name,
            "credit_limit": credit_limit,
            "current_balance": current_balance or 0.0,
            "usage_rate": usage_rate or 0.0,
            "level": level,
            "statement_date": br.statement_date if br else None,
            "due_date": br.due_date if br else None,
        })

    return results


@router.get("/cashback-estimate", summary="返现/积分估算")
async def cashback_estimate(
    year: Optional[int] = Query(None, description="年（默认当年当月）"),
    month: Optional[int] = Query(None, description="月", ge=1, le=12),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """根据本月消费品类匹配用户持有卡的权益，估算返现/积分。"""
    user_id = user["user_id"]

    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # 1. 本月各品类消费汇总
    cat_stmt = (
        select(ExpenseRecord.category, func.coalesce(func.sum(ExpenseRecord.amount), 0.0))
        .where(
            ExpenseRecord.user_id == user_id,
            ExpenseRecord.is_refund == False,
            extract("year", ExpenseRecord.expense_date) == year,
            extract("month", ExpenseRecord.expense_date) == month,
        )
        .group_by(ExpenseRecord.category)
    )
    cat_spending = {row[0]: row[1] for row in (await db.execute(cat_stmt)).all()}

    # 2. 获取用户所有卡及其权益
    uc_result = await db.execute(
        select(UserCard).where(UserCard.user_id == user_id, UserCard.is_active == True)
    )
    user_cards = uc_result.scalars().all()

    total_estimated_cashback = 0.0
    total_estimated_points = 0.0
    card_estimates = []

    for uc in user_cards:
        if not uc.card_id:
            continue

        # 查卡信息和权益
        card_result = await db.execute(
            select(CreditCard).where(CreditCard.id == uc.card_id)
        )
        card_info = card_result.scalar()
        if not card_info:
            continue

        benefit_result = await db.execute(
            select(CardBenefit).where(
                CardBenefit.card_id == uc.card_id,
                CardBenefit.is_active == True,
            )
        )
        benefits = benefit_result.scalars().all()

        card_cashback = 0.0
        card_points = 0.0
        matched = []

        for benefit in benefits:
            if benefit.benefit_type not in (BenefitType.CASHBACK, BenefitType.POINTS):
                continue
            benefit_cats = CATEGORY_TO_BENEFIT.get(benefit.category.value, [benefit.category.value])
            # 检查是否匹配用户实际消费类别
            for exp_cat, amount in cat_spending.items():
                if benefit.category == BenefitCategory.GENERAL:
                    # 通用权益匹配所有品类
                    is_match = True
                else:
                    is_match = any(bc == exp_cat for bc in benefit_cats) or \
                               any(bc in exp_cat or exp_cat in bc for bc in benefit_cats)
                if not is_match:
                    continue

                est_cashback = 0.0
                est_points = 0.0
                if benefit.benefit_type == BenefitType.CASHBACK and benefit.cashback_percent:
                    est_cashback = round(amount * benefit.cashback_percent / 100, 2)
                    card_cashback += est_cashback
                if benefit.benefit_type == BenefitType.POINTS and benefit.points_per_yuan:
                    est_points = round(amount * benefit.points_per_yuan, 0)
                    card_points += est_points

                if est_cashback > 0 or est_points > 0:
                    matched.append({
                        "benefit_title": benefit.title,
                        "benefit_type": benefit.benefit_type.value,
                        "category": benefit.category.value,
                        "expense_category": exp_cat,
                        "spending_amount": round(amount, 2),
                        "estimated_cashback": est_cashback,
                        "estimated_points": est_points,
                        "rate": f"{benefit.cashback_percent}%返现" if benefit.cashback_percent else f"{benefit.points_per_yuan}积分/元",
                    })

        total_estimated_cashback += card_cashback
        total_estimated_points += card_points

        if matched:
            card_estimates.append({
                "user_card_id": uc.id,
                "bank": card_info.bank,
                "card_name": uc.nickname or card_info.name,
                "estimated_cashback": round(card_cashback, 2),
                "estimated_points": round(card_points, 0),
                "matched_benefits": matched,
            })

    return {
        "year": year,
        "month": month,
        "total_spending": round(sum(cat_spending.values()), 2),
        "total_estimated_cashback": round(total_estimated_cashback, 2),
        "total_estimated_points": round(total_estimated_points, 0),
        "cards": card_estimates,
    }
