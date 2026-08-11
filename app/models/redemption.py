from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Float, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RedemptionItem(Base):
    __tablename__ = "redemption_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("credit_cards.id"), nullable=True, index=True)
    item_name: Mapped[str] = mapped_column(String(256), index=True)
    merchant_name: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(64), index=True)
    points_required: Mapped[int] = mapped_column(Integer)
    cash_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())