"""账单与额度管理 API。"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.services import bill_service
from app.schemas.bill import (
    BillCreate,
    BillPay,
    BillRecurringUpdate,
    ExpenseCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bills", tags=["账单与额度管理"])


# ── 账单 ──────────────────────────────────────────

@router.get("/summary", summary="账单总览")
async def bill_summary(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """汇总所有卡的账单状态：总额度、总欠款、使用率、本月应还等。"""
    return await bill_service.get_bill_summary(user["user_id"], db)


@router.get("/upcoming", summary="近期还款提醒")
async def upcoming_bills(
    user: dict = Depends(get_current_user),
    within_days: int = Query(7, ge=1, le=60, description="未来N天内到期的还款"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回未来 N 天内到期的未还账单。"""
    return await bill_service.get_upcoming_bills(user["user_id"], within_days, db)


@router.get("/card/{user_card_id}", summary="某卡账单")
async def card_bills(
    user_card_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """某张卡的所有账单记录（倒序）。"""
    return await bill_service.get_card_bills(user_card_id, db)


@router.post("", summary="录入账单")
async def create_bill(
    body: BillCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """录入一笔账单，自动从 user_card 同步额度。"""
    data = body.model_dump()
    data["user_id"] = user["user_id"]
    bill = await bill_service.create_bill(data, db)
    return bill_service._bill_to_dict(bill)


@router.patch("/{bill_id}/pay", summary="标记还款")
async def pay_bill(
    bill_id: str,
    body: BillPay = BillPay(),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """标记账单为已还款。"""
    bill = await bill_service.pay_bill(bill_id, body.paid_date, db)
    if not bill:
        raise HTTPException(status_code=404, detail="账单不存在")
    return bill_service._bill_to_dict(bill)


@router.patch("/{user_card_id}/recurring", summary="设置定期账单")
async def update_recurring(
    user_card_id: str,
    body: BillRecurringUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """更新某卡所有未还账单的账单日/还款日。"""
    bills = await bill_service.update_bill_recurring(
        user_card_id, body.statement_date, body.due_date, db,
    )
    return {"ok": True, "updated_count": len(bills), "bills": bills}


# ── 消费 ──────────────────────────────────────────

@router.get("/expenses/card/{user_card_id}", summary="某卡消费")
async def card_expenses(
    user_card_id: str,
    month: str | None = Query(None, description="筛选月份 YYYY-MM"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """某卡消费记录，可选按月筛选。"""
    return await bill_service.get_expenses(user_card_id, db, month=month)


@router.get("/expenses/stats", summary="消费统计")
async def expense_stats(
    user: dict = Depends(get_current_user),
    month: str | None = Query(None, description="筛选月份 YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """消费统计：按类别汇总 + 按卡汇总 + 总消费。"""
    return await bill_service.get_expense_stats(user["user_id"], db, month=month)


@router.post("/expenses", summary="录入消费")
async def create_expense(
    body: ExpenseCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """新增一笔消费记录。"""
    data = body.model_dump()
    data["user_id"] = user["user_id"]
    exp = await bill_service.add_expense(data, db)
    return bill_service._expense_to_dict(exp)
