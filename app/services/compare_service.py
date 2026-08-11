"""多卡对比服务：横向对比多张信用卡"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.card import CreditCard
from app.models.benefit import CardBenefit, BenefitCategory, BenefitType
from app.schemas.recommend import (
    CardCompareItem,
    CardDimensionScore,
    CompareResponse,
)
from app.schemas.card import CardOut, BenefitOut


def _score_dimensions(benefits: list[CardBenefit]) -> CardDimensionScore:
    """根据权益列表计算四维度得分（归一化 0~10）。"""
    cashback = 0.0
    discount = 0.0
    points = 0.0
    benefit_count = len(benefits)

    for b in benefits:
        if b.cashback_percent:
            cashback += b.cashback_percent
        if b.discount_percent:
            discount += b.discount_percent
        if b.points_per_yuan:
            points += b.points_per_yuan

    # 归一化到 0~10
    cashback = min(cashback * 2.0, 10.0)
    discount = min(discount / 5.0, 10.0)
    points = min(points * 2.0, 10.0)
    benefit_count_score = min(benefit_count * 1.5, 10.0)

    return CardDimensionScore(
        cashback=round(cashback, 2),
        discount=round(discount, 2),
        points=round(points, 2),
        benefit_count=round(benefit_count_score, 2),
    )


async def compare_cards(
    card_ids: list[str],
    scenario: str | None,
    db: AsyncSession,
) -> CompareResponse:
    """多卡对比。

    返回每张卡的基本信息、权益对比、综合评分和胜出推荐。
    scenario 非空时只对比该场景相关权益。
    """
    # 1. 查询卡片（含权益预加载）
    stmt = (
        select(CreditCard)
        .options(joinedload(CreditCard.benefits))
        .where(CreditCard.id.in_(card_ids), CreditCard.is_active == True)
    )
    result = await db.execute(stmt)
    cards = result.unique().scalars().all()

    # 保持传入顺序
    cards_map = {c.id: c for c in cards}
    ordered_cards = [cards_map[cid] for cid in card_ids if cid in cards_map]

    # 2. 如果有场景，解析场景类别过滤权益
    relevant_categories: set[BenefitCategory] | None = None
    if scenario:
        from app.services.recommend_service import _parse_scenario, _match_category
        labels = _parse_scenario(scenario)
        relevant_categories = set()
        for label in labels:
            cat = _match_category(label)
            if cat:
                relevant_categories.add(cat)

    # 3. 构建对比结果
    compare_items: list[CardCompareItem] = []
    for card in ordered_cards:
        # 按场景过滤权益
        if relevant_categories:
            filtered_benefits = [
                b for b in card.benefits
                if b.category in relevant_categories and b.is_active
            ]
        else:
            filtered_benefits = [b for b in card.benefits if b.is_active]

        scores = _score_dimensions(filtered_benefits)
        total_score = round(
            scores.cashback + scores.discount + scores.points + scores.benefit_count,
            2,
        )

        compare_items.append(CardCompareItem(
            card=CardOut.model_validate(card),
            benefits=[BenefitOut.model_validate(b) for b in filtered_benefits],
            scores=scores,
            total_score=total_score,
        ))

    # 4. 找出胜出者
    winner = None
    winner_reason = None
    if compare_items:
        # 按总分降序
        sorted_items = sorted(compare_items, key=lambda x: x.total_score, reverse=True)
        best = sorted_items[0]
        winner = best
        card_name = f"{best.card.bank}{best.card.name}"
        dims = best.scores
        # 找出最强维度
        dim_names = []
        if dims.cashback >= 5:
            dim_names.append("返现")
        if dims.discount >= 5:
            dim_names.append("折扣")
        if dims.points >= 5:
            dim_names.append("积分")
        if dims.benefit_count >= 5:
            dim_names.append("权益数量")

        if len(compare_items) == 1:
            winner_reason = f"{card_name} 是唯一参比卡片"
        elif dim_names:
            winner_reason = f"{card_name} 综合得分最高，在{'、'.join(dim_names)}方面表现突出"
        else:
            winner_reason = f"{card_name} 综合得分最高（{best.total_score} 分）"

    return CompareResponse(
        scenario=scenario,
        cards=compare_items,
        winner=winner,
        winner_reason=winner_reason,
    )
