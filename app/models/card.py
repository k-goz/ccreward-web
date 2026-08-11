import enum
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CardNetwork(str, enum.Enum):
    UNIONPAY = "银联"
    VISA = "Visa"
    MASTERCARD = "Mastercard"
    AMEX = "美国运通"
    JCB = "JCB"


class CardLevel(str, enum.Enum):
    CLASSIC = "经典版"
    GOLD = "金卡"
    PLATINUM = "白金卡"
    DIAMOND = "钻石卡"
    SIGNATURE = "御尊卡"
    INFINITE = "无限卡"


class CreditCard(Base):
    __tablename__ = "credit_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bank: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    network: Mapped[CardNetwork] = mapped_column(Enum(CardNetwork), default=CardNetwork.UNIONPAY)
    level: Mapped[CardLevel] = mapped_column(Enum(CardLevel), default=CardLevel.CLASSIC)
    annual_fee: Mapped[str] = mapped_column(String(64), default="免首年年费")
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    benefits: Mapped[list["CardBenefit"]] = relationship(back_populates="card", cascade="all, delete-orphan")