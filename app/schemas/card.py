from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.models.card import CardNetwork, CardLevel
from app.models.benefit import BenefitType, BenefitCategory


class CardBase(BaseModel):
    bank: str
    name: str
    network: CardNetwork = CardNetwork.UNIONPAY
    level: CardLevel = CardLevel.CLASSIC
    annual_fee: str = "免首年年费"
    image_url: str | None = None
    description: str | None = None


class CardCreate(CardBase):
    id: str


class CardOut(CardBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
    created_at: datetime


class BenefitBase(BaseModel):
    title: str
    benefit_type: BenefitType
    category: BenefitCategory = BenefitCategory.GENERAL
    description: str
    value_text: str | None = None
    points_per_yuan: float | None = None
    discount_percent: float | None = None
    cashback_percent: float | None = None
    usage_limit: str | None = None
    merchant_tags: str | None = None


class BenefitCreate(BenefitBase):
    id: str
    card_id: str


class BenefitOut(BenefitBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    card_id: str
    is_active: bool


class CardWithBenefits(CardOut):
    benefits: list[BenefitOut] = []