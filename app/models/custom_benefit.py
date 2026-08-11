"""用户自定义权益模型 — 权益覆盖与自定义兑换项。"""

import uuid
from datetime import datetime, date

from sqlalchemy import String, Text, DateTime, Date, ForeignKey, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserBenefitOverride(Base):
    """用户对某张卡的权益自定义覆盖或额外权益。"""

    __tablename__ = "user_benefit_overrides"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_card_id: Mapped[str] = mapped_column(ForeignKey("user_cards.id"), index=True)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("credit_cards.id"), nullable=True)

    # 如果是覆盖种子权益（nullable=可以新增额外权益）
    benefit_id: Mapped[str | None] = mapped_column(ForeignKey("card_benefits.id"), nullable=True)

    # 覆盖字段（只填要改的）
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefit_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # BenefitType enum value
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # BenefitCategory enum value
    discount_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    cashback_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    points_per_yuan: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    usage_limit: Mapped[str | None] = mapped_column(String(256), nullable=True)
    merchant_tags: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class UserRedemptionOverride(Base):
    """用户自定义积分兑换项。"""

    __tablename__ = "user_redemption_overrides"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_card_id: Mapped[str] = mapped_column(ForeignKey("user_cards.id"), index=True)
    card_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    item_name: Mapped[str] = mapped_column(String(256))
    merchant_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    points_required: Mapped[float] = mapped_column(Float)
    cash_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
