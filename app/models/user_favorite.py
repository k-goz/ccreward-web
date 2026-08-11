"""用户收藏与搜索历史模型。"""

from datetime import datetime

from sqlalchemy import String, DateTime, Boolean, Integer, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserFavorite(Base):
    """用户收藏的活动/卡片。"""

    __tablename__ = "user_favorites"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(32), default="activity")  # activity | card
    target_title: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserSearchHistory(Base):
    """用户搜索历史。"""

    __tablename__ = "user_search_history"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    keyword: Mapped[str] = mapped_column(String(256))
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
