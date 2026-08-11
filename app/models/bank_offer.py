"""银行优惠（Bank Offer）：各行信用卡实时优惠活动聚合。"""
import enum
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OfferStatus(str, enum.Enum):
    ACTIVE = "进行中"
    REGULAR = "常态活动"
    EXPIRED = "已过期"


class BankOffer(Base):
    __tablename__ = "bank_offers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bank: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text)
    discount_highlight: Mapped[str | None] = mapped_column(String(128), nullable=True)
    how_to_join: Mapped[str | None] = mapped_column(Text, nullable=True)
    jump_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    valid_period: Mapped[str | None] = mapped_column(String(128), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[OfferStatus] = mapped_column(String(8), default=OfferStatus.ACTIVE, index=True)
    applicable_cards: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
