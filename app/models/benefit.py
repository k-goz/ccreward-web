import enum
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Integer, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BenefitType(str, enum.Enum):
    CASHBACK = "返现"
    POINTS = "积分累积"
    DISCOUNT = "折扣"
    BUY_ONE_GET_ONE = "买一赠一"
    FREE_GIFT = "赠礼"
    LOUNGE = "贵宾厅"
    PRIORITY = "优先权益"
    INSURANCE = "保险"
    OTHER = "其他"


class BenefitCategory(str, enum.Enum):
    DINING = "餐饮美食"
    COFFEE = "咖啡茶饮"
    SHOPPING = "购物消费"
    ONLINE = "线上消费"
    TRAVEL = "出行旅游"
    PETROL = "加油"
    ENTERTAINMENT = "休闲娱乐"
    GROCERY = "超市便利"
    BILL = "生活缴费"
    GENERAL = "通用"


class CardBenefit(Base):
    __tablename__ = "card_benefits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("credit_cards.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    benefit_type: Mapped[BenefitType] = mapped_column(Enum(BenefitType))
    category: Mapped[BenefitCategory] = mapped_column(Enum(BenefitCategory), default=BenefitCategory.GENERAL)
    description: Mapped[str] = mapped_column(Text)
    value_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    points_per_yuan: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    cashback_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_limit: Mapped[str | None] = mapped_column(String(256), nullable=True)
    merchant_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    card: Mapped["CreditCard"] = relationship(back_populates="benefits")