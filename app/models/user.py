"""用户卡片模型 — 我的卡包。"""

from datetime import datetime

from sqlalchemy import String, Text, DateTime, Boolean, Float, Integer, Date, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserCard(Base):
    """用户实际持有的信用卡。"""

    __tablename__ = "user_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    card_id: Mapped[str] = mapped_column(String(64), index=True)  # 关联 credit_cards.id，自定义卡时为空
    nickname: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 实际持卡信息
    last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)  # 卡号后四位
    credit_limit: Mapped[float | None] = mapped_column(Float, nullable=True)  # 额度（元）
    issue_date: Mapped[str | None] = mapped_column(String(7), nullable=True)  # 办卡日期 YYYY-MM
    expire_date: Mapped[str | None] = mapped_column(String(7), nullable=True)  # 到期月 YYYY-MM
    annual_fee_condition: Mapped[str | None] = mapped_column(String(256), nullable=True)  # 年费减免条件
    annual_fee_waived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 当年年费是否已减免
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # 排序（越小越靠前）
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # 备注

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
