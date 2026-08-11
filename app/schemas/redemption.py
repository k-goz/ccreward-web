from pydantic import BaseModel, ConfigDict


class RedemptionBase(BaseModel):
    item_name: str
    merchant_name: str
    category: str
    points_required: int
    cash_value: float | None = None
    description: str | None = None


class RedemptionCreate(RedemptionBase):
    id: str
    card_id: str | None = None


class RedemptionOut(RedemptionBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    card_id: str | None
    is_active: bool