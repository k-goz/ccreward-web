"""账单与额度管理服务层。

功能：
- 账单总览（总额度/总欠款/使用率）
- 单卡账单管理（创建/标记还款/更新定期账单日）
- 近期还款提醒
- 消费记录（录入/按月筛选）
- 消费统计（按类别/按卡汇总）
"""

import uuid
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import BillRecord, ExpenseRecord
from app.models.user import UserCard
from app.models.card import CreditCard

logger = logging.getLogger(__name__)

# ── 公共分类列表 ───────────────────────────────────
EXPENSE_CATEGORIES = ["餐饮", "购物", "出行", "娱乐", "生活", "其他"]


# ── 账单总览 ──────────────────────────────────────

async def get_bill_summary(user_id: str, db: AsyncSession) -> dict:
    """汇总所有卡的账单状态。"""
    # 查询该用户所有账单
    stmt = select(BillRecord).where(BillRecord.user_id == user_id)
    result = await db.execute(stmt)
    bills = result.scalars().all()

    unpaid = [b for b in bills if not b.is_paid]
    paid = [b for b in bills if b.is_paid]

    total_limit = sum(b.credit_limit or 0 for b in bills)
    total_balance = sum(b.current_balance or 0 for b in unpaid)
    due_this_month = sum(b.current_balance or 0 for b in unpaid)
    overall_usage_rate = round((total_balance / total_limit * 100), 1) if total_limit > 0 else 0.0

    # 涉及卡数（去重）
    card_ids = set(b.user_card_id for b in bills)

    return {
        "total_credit_limit": total_limit,
        "total_balance": total_balance,
        "overall_usage_rate": overall_usage_rate,
        "due_this_month": due_this_month,
        "unpaid_count": len(unpaid),
        "paid_count": len(paid),
        "total_cards": len(card_ids),
    }


# ── 单卡账单 ──────────────────────────────────────

async def get_card_bills(user_card_id: str, db: AsyncSession) -> list[dict]:
    """某张卡的所有账单记录，按创建时间倒序。"""
    stmt = (
        select(BillRecord)
        .where(BillRecord.user_card_id == user_card_id)
        .order_by(BillRecord.created_at.desc())
    )
    result = await db.execute(stmt)
    bills = result.scalars().all()
    return [_bill_to_dict(b) for b in bills]


async def create_bill(data: dict, db: AsyncSession) -> BillRecord:
    """录入账单，自动从 user_card 同步额度（如果 data 中未提供）。"""
    user_card_id = data["user_card_id"]
    user_id = data["user_id"]

    # 同步额度
    credit_limit = data.get("credit_limit")
    if credit_limit is None:
        uc = await db.get(UserCard, user_card_id)
        if uc and uc.credit_limit:
            credit_limit = uc.credit_limit

    # 自动计算使用率
    current_balance = data.get("current_balance")
    usage_rate = None
    if credit_limit and credit_limit > 0 and current_balance is not None:
        usage_rate = round(current_balance / credit_limit * 100, 1)

    bill = BillRecord(
        id=str(uuid.uuid4()),
        user_id=user_id,
        user_card_id=user_card_id,
        card_id=data.get("card_id"),
        statement_date=data["statement_date"],
        due_date=data["due_date"],
        current_balance=current_balance,
        min_payment=data.get("min_payment"),
        credit_limit=credit_limit,
        usage_rate=usage_rate,
        notes=data.get("notes"),
    )
    db.add(bill)
    await db.commit()
    await db.refresh(bill)
    logger.info(f"账单创建: bill={bill.id}, card={user_card_id}, balance={bill.current_balance}")
    return bill


async def pay_bill(bill_id: str, paid_date: date | None, db: AsyncSession) -> BillRecord | None:
    """标记已还款。"""
    bill = await db.get(BillRecord, bill_id)
    if not bill:
        return None
    bill.is_paid = True
    bill.paid_date = paid_date or date.today()
    await db.commit()
    await db.refresh(bill)
    logger.info(f"还款标记: bill={bill_id}, paid_date={bill.paid_date}")
    return bill


async def update_bill_recurring(
    user_card_id: str,
    statement_date: int,
    due_date: int,
    db: AsyncSession,
) -> list[dict]:
    """更新某卡所有未还账单的账单日/还款日，并返回更新后的列表。"""
    stmt = select(BillRecord).where(
        and_(
            BillRecord.user_card_id == user_card_id,
            BillRecord.is_paid == False,
        )
    )
    result = await db.execute(stmt)
    bills = result.scalars().all()
    for b in bills:
        b.statement_date = statement_date
        b.due_date = due_date
    await db.commit()
    logger.info(f"定期账单更新: card={user_card_id}, 更新了 {len(bills)} 条未还账单")
    return [_bill_to_dict(b) for b in bills]


async def get_upcoming_bills(
    user_id: str,
    within_days: int,
    db: AsyncSession,
) -> list[dict]:
    """未来 N 天内到期的还款（按还款日估算）。"""
    today = date.today()
    stmt = (
        select(BillRecord)
        .where(
            and_(
                BillRecord.user_id == user_id,
                BillRecord.is_paid == False,
            )
        )
    )
    result = await db.execute(stmt)
    bills = result.scalars().all()

    upcoming = []
    for b in bills:
        # 估算下一个还款日
        next_due = _estimate_next_date(b.due_date, today)
        if next_due is None:
            continue
        diff = (next_due - today).days
        if 0 <= diff <= within_days:
            item = _bill_to_dict(b)
            item["estimated_due_date"] = next_due.isoformat()
            item["days_remaining"] = diff
            upcoming.append(item)

    upcoming.sort(key=lambda x: x["days_remaining"])
    return upcoming


# ── 消费记录 ──────────────────────────────────────

async def get_expenses(
    user_card_id: str,
    db: AsyncSession,
    month: str | None = None,
) -> list[dict]:
    """某卡消费记录，可选按月筛选。month 格式 YYYY-MM。"""
    stmt = select(ExpenseRecord).where(
        ExpenseRecord.user_card_id == user_card_id,
    )
    if month:
        year, mon = month.split("-")
        stmt = stmt.where(
            and_(
                extract("year", ExpenseRecord.expense_date) == int(year),
                extract("month", ExpenseRecord.expense_date) == int(mon),
            )
        )
    stmt = stmt.order_by(ExpenseRecord.expense_date.desc())
    result = await db.execute(stmt)
    expenses = result.scalars().all()
    return [_expense_to_dict(e) for e in expenses]


async def add_expense(data: dict, db: AsyncSession) -> ExpenseRecord:
    """新增消费记录。"""
    exp = ExpenseRecord(
        id=str(uuid.uuid4()),
        user_id=data["user_id"],
        user_card_id=data["user_card_id"],
        card_id=data.get("card_id"),
        amount=data["amount"],
        category=data["category"],
        merchant=data.get("merchant"),
        description=data.get("description"),
        expense_date=data["expense_date"],
        is_refund=data.get("is_refund", False),
        notes=data.get("notes"),
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    logger.info(f"消费记录: {exp.id}, amount={exp.amount}, category={exp.category}")
    return exp


async def get_expense_stats(
    user_id: str,
    db: AsyncSession,
    month: str | None = None,
) -> dict:
    """消费统计 — 按类别汇总 + 按卡汇总 + 总消费。"""
    stmt = select(ExpenseRecord).where(
        and_(
            ExpenseRecord.user_id == user_id,
            ExpenseRecord.is_refund == False,
        )
    )
    if month:
        year, mon = month.split("-")
        stmt = stmt.where(
            and_(
                extract("year", ExpenseRecord.expense_date) == int(year),
                extract("month", ExpenseRecord.expense_date) == int(mon),
            )
        )

    result = await db.execute(stmt)
    expenses = result.scalars().all()

    total_spent = sum(e.amount for e in expenses)

    # 按类别汇总
    cat_map: dict[str, dict[str, Any]] = {}
    for e in expenses:
        if e.category not in cat_map:
            cat_map[e.category] = {"total": 0.0, "count": 0}
        cat_map[e.category]["total"] += e.amount
        cat_map[e.category]["count"] += 1

    by_category = [
        {
            "category": cat,
            "total": round(info["total"], 2),
            "count": info["count"],
            "pct": round(info["total"] / total_spent * 100, 1) if total_spent > 0 else 0.0,
        }
        for cat, info in sorted(cat_map.items(), key=lambda x: x[1]["total"], reverse=True)
    ]

    # 按卡汇总
    card_map: dict[str, dict[str, Any]] = {}
    for e in expenses:
        if e.user_card_id not in card_map:
            card_map[e.user_card_id] = {"total": 0.0, "count": 0}
        card_map[e.user_card_id]["total"] += e.amount
        card_map[e.user_card_id]["count"] += 1

    by_card = [
        {
            "user_card_id": cid,
            "total": round(info["total"], 2),
            "count": info["count"],
            "pct": round(info["total"] / total_spent * 100, 1) if total_spent > 0 else 0.0,
        }
        for cid, info in sorted(card_map.items(), key=lambda x: x[1]["total"], reverse=True)
    ]

    return {
        "total_spent": round(total_spent, 2),
        "total_count": len(expenses),
        "by_category": by_category,
        "by_card": by_card,
    }


# ── 内部工具 ──────────────────────────────────────

def _bill_to_dict(b: BillRecord) -> dict:
    return {
        "id": b.id,
        "user_id": b.user_id,
        "user_card_id": b.user_card_id,
        "card_id": b.card_id,
        "statement_date": b.statement_date,
        "due_date": b.due_date,
        "current_balance": b.current_balance,
        "min_payment": b.min_payment,
        "credit_limit": b.credit_limit,
        "usage_rate": b.usage_rate,
        "is_paid": b.is_paid,
        "paid_date": b.paid_date.isoformat() if b.paid_date else None,
        "notes": b.notes,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _expense_to_dict(e: ExpenseRecord) -> dict:
    return {
        "id": e.id,
        "user_id": e.user_id,
        "user_card_id": e.user_card_id,
        "card_id": e.card_id,
        "amount": e.amount,
        "category": e.category,
        "merchant": e.merchant,
        "description": e.description,
        "expense_date": e.expense_date.isoformat() if e.expense_date else None,
        "is_refund": e.is_refund,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _estimate_next_date(day_of_month: int, today: date) -> date | None:
    """估算下一个目标日期（账单日/还款日）。"""
    if not 1 <= day_of_month <= 31:
        return None
    try:
        candidate = today.replace(day=min(day_of_month, _days_in_month(today.year, today.month)))
    except ValueError:
        return None
    if candidate < today:
        next_month = today.month + 1
        next_year = today.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        try:
            candidate = today.replace(
                year=next_year,
                month=next_month,
                day=min(day_of_month, _days_in_month(next_year, next_month)),
            )
        except ValueError:
            return None
    return candidate


def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]
