"""权益使用追踪模型 — 记录每项权益的月度/年度使用次数，支撑到期提醒。"""

import uuid
from datetime import datetime, date

from sqlalchemy import String, Integer, Date, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BenefitUsageTrack(Base):
    __tablename__ = "benefit_usage_tracks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    user_card_id: Mapped[str] = mapped_column(ForeignKey("user_cards.id"), index=True)
    benefit_id: Mapped[str] = mapped_column(ForeignKey("card_benefits.id"), index=True)
    benefit_title: Mapped[str] = mapped_column(String(256))

    monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_this_month: Mapped[int] = mapped_column(Integer, default=0)
    last_used_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_reset_month: Mapped[str | None] = mapped_column(String(7), nullable=True)  # YYYY-MM

    year_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_this_year: Mapped[int] = mapped_column(Integer, default=0)
    total_used: Mapped[int] = mapped_column(Integer, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
