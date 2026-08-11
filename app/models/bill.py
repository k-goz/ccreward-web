"""账单与额度管理模型。"""

from datetime import date, datetime

from sqlalchemy import String, Text, DateTime, Date, ForeignKey, Float, Boolean, Integer, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillRecord(Base):
    """账单记录 — 每张用户卡每期的账单。"""

    __tablename__ = "bill_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_card_id: Mapped[str] = mapped_column(ForeignKey("user_cards.id"), index=True)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("credit_cards.id"), nullable=True)
    statement_date: Mapped[int] = mapped_column(Integer)  # 账单日 1-28
    due_date: Mapped[int] = mapped_column(Integer)  # 还款日 1-31
    current_balance: Mapped[float | None] = mapped_column(Float, nullable=True)  # 本期账单金额
    min_payment: Mapped[float | None] = mapped_column(Float, nullable=True)  # 最低还款额
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)  # 额度
    usage_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 额度使用率(%)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)  # 本期已还
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 还款日期
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ExpenseRecord(Base):
    """消费记录 — 每笔消费明细。"""

    __tablename__ = "expense_records"
    __table_args__ = (
        Index("ix_expense_records_user_date", "user_id", "expense_date"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_card_id: Mapped[str] = mapped_column(ForeignKey("user_cards.id"), index=True)
    card_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[float] = mapped_column(Float)  # 金额
    category: Mapped[str] = mapped_column(String(32))  # 餐饮/购物/出行/娱乐/生活/其他
    merchant: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 商户名
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)  # 消费日期
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
