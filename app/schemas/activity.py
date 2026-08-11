from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ActivityBase(BaseModel):
    title: str
    platform: str
    merchant_name: str
    category: str
    product_name: str | None = None
    original_price: float | None = None
    activity_price: float | None = None
    discount_description: str
    usage_conditions: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_url: str | None = None
    app_url: str | None = None
    image_url: str | None = None


class ActivityCreate(ActivityBase):
    id: str


class ActivityOut(ActivityBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    source_type: str
    created_at: datetime


class PriceComparisonItem(BaseModel):
    platform: str
    platform_label: str
    activity_id: str
    title: str
    activity_price: float | None
    original_price: float | None
    discount_description: str
    usage_conditions: str | None
    source_url: str | None
    app_url: str | None
    is_cheapest: bool = False


class PriceComparisonResult(BaseModel):
    keyword: str
    total_platforms: int
    cheapest_platform: str | None
    cheapest_price: float | None
    items: list[PriceComparisonItem]
