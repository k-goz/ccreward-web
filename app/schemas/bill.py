"""账单与额度管理 schemas。"""

from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict


# ── 账单 ──────────────────────────────────────────

class BillCreate(BaseModel):
    user_card_id: str
    card_id: str | None = None
    statement_date: int = Field(..., ge=1, le=28, description="账单日 1-28")
    due_date: int = Field(..., ge=1, le=31, description="还款日 1-31")
    current_balance: float | None = None
    min_payment: float | None = None
    credit_limit: float | None = None
    notes: str | None = None


class BillPay(BaseModel):
    paid_date: date | None = Field(None, description="还款日期，默认今天")


class BillRecurringUpdate(BaseModel):
    statement_date: int = Field(..., ge=1, le=28)
    due_date: int = Field(..., ge=1, le=31)


class BillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    user_card_id: str
    card_id: str | None
    statement_date: int
    due_date: int
    current_balance: float | None
    min_payment: float | None
    credit_limit: float | None
    usage_rate: float | None
    is_paid: bool
    paid_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class BillSummary(BaseModel):
    total_credit_limit: float  # 总额度
    total_balance: float  # 总欠款（未还部分）
    overall_usage_rate: float  # 总体使用率 (%)
    due_this_month: float  # 本月应还
    unpaid_count: int  # 未还账单数
    paid_count: int  # 已还账单数
    total_cards: int  # 涉及卡数


# ── 消费 ──────────────────────────────────────────

class ExpenseCreate(BaseModel):
    user_card_id: str
    card_id: str | None = None
    amount: float = Field(..., gt=0, description="金额")
    category: str = Field(..., description="餐饮/购物/出行/娱乐/生活/其他")
    merchant: str | None = None
    description: str | None = None
    expense_date: date
    is_refund: bool = False
    notes: str | None = None


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    user_card_id: str
    card_id: str | None
    amount: float
    category: str
    merchant: str | None
    description: str | None
    expense_date: date
    is_refund: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ── 消费统计 ───────────────────────────────────────

class CategoryBreakdown(BaseModel):
    category: str
    total: float
    count: int
    pct: float  # 占总消费百分比


class CardBreakdown(BaseModel):
    user_card_id: str
    total: float
    count: int
    pct: float


class ExpenseStats(BaseModel):
    total_spent: float
    total_count: int
    by_category: list[CategoryBreakdown]
    by_card: list[CardBreakdown]
