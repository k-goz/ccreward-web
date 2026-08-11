"""推荐 & 多卡对比 Schema"""

from pydantic import BaseModel

from app.schemas.card import CardOut, BenefitOut


class MatchedBenefit(BaseModel):
    """匹配到的权益摘要"""
    id: str
    title: str
    benefit_type: str
    category: str
    description: str
    discount_percent: float | None = None
    cashback_percent: float | None = None
    points_per_yuan: float | None = None
    score_contribution: float = 0.0  # 该权益对总分的贡献


class RecommendResult(BaseModel):
    """单张卡推荐结果"""
    card: CardOut
    total_score: float
    matched_benefits: list[MatchedBenefit]
    reason: str


class RecommendResponse(BaseModel):
    """场景推荐响应"""
    scenario: str
    matched_categories: list[str]
    recommendations: list[RecommendResult]


class CardDimensionScore(BaseModel):
    """单维度得分明细"""
    cashback: float
    discount: float
    points: float
    benefit_count: float


class CardCompareItem(BaseModel):
    """多卡对比中单张卡的数据"""
    card: CardOut
    benefits: list[BenefitOut]
    scores: CardDimensionScore
    total_score: float


class CompareResponse(BaseModel):
    """多卡对比响应"""
    scenario: str | None = None
    cards: list[CardCompareItem]
    winner: CardCompareItem | None = None
    winner_reason: str | None = None
