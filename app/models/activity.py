import enum
from datetime import datetime

from sqlalchemy import String, Text, DateTime, Float, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Platform(str, enum.Enum):
    DOUYIN = "抖音"
    MEITUAN = "美团"
    DIDI = "滴滴"
    TAOBAO = "淘宝"
    JD = "京东"
    PINDUODUO = "拼多多"
    ALIPAY = "支付宝"
    WECHAT = "微信"
    KOUWEI = "口碑"
    ELEME = "饿了么"
    VIPSHOP = "唯品会"
    SUNING = "苏宁"
    OTHER = "其他"


class ActivityStatus(str, enum.Enum):
    ACTIVE = "进行中"
    EXPIRED = "已过期"
    UPCOMING = "未开始"


class MerchantActivity(Base):
    __tablename__ = "merchant_activities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    platform: Mapped[Platform] = mapped_column(String(9), index=True)
    merchant_name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_description: Mapped[str] = mapped_column(Text)
    usage_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    status: Mapped[ActivityStatus] = mapped_column(String(8), default=ActivityStatus.ACTIVE, index=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    app_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
