"""商家活动服务层：搜索、比价、统计。"""

from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import MerchantActivity, ActivityStatus, Platform
from app.schemas.activity import ActivityOut, PriceComparisonItem, PriceComparisonResult


async def search_activities(
    db: AsyncSession,
    keyword: str | None = None,
    platform: Platform | None = None,
    category: str | None = None,
    sort: str = "updated",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """搜索商家活动，返回分页结果。"""
    base_stmt = select(MerchantActivity).where(
        MerchantActivity.is_active == True,
        MerchantActivity.status == ActivityStatus.ACTIVE,
    )
    count_stmt = select(func.count(MerchantActivity.id)).where(
        MerchantActivity.is_active == True,
        MerchantActivity.status == ActivityStatus.ACTIVE,
    )

    if keyword:
        like = f"%{keyword}%"
        base_stmt = base_stmt.where(
            or_(
                MerchantActivity.title.ilike(like),
                MerchantActivity.merchant_name.ilike(like),
                MerchantActivity.product_name.ilike(like),
                MerchantActivity.discount_description.ilike(like),
            )
        )
        count_stmt = count_stmt.where(
            or_(
                MerchantActivity.title.ilike(like),
                MerchantActivity.merchant_name.ilike(like),
                MerchantActivity.product_name.ilike(like),
                MerchantActivity.discount_description.ilike(like),
            )
        )
    if platform:
        base_stmt = base_stmt.where(MerchantActivity.platform == platform)
        count_stmt = count_stmt.where(MerchantActivity.platform == platform)
    if category:
        base_stmt = base_stmt.where(MerchantActivity.category == category)
        count_stmt = count_stmt.where(MerchantActivity.category == category)

    # 排序
    if sort == "price":
        base_stmt = base_stmt.order_by(
            MerchantActivity.activity_price.asc().nullslast()
        )
    else:
        base_stmt = base_stmt.order_by(MerchantActivity.updated_at.desc())

    # 总数
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 分页
    base_stmt = base_stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(base_stmt)
    items = [ActivityOut.model_validate(a) for a in result.scalars().all()]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


async def compare_prices(db: AsyncSession, keyword: str) -> PriceComparisonResult:
    """同一商品多平台比价。"""
    stmt = (
        select(MerchantActivity)
        .where(
            MerchantActivity.is_active == True,
            MerchantActivity.status == ActivityStatus.ACTIVE,
            or_(
                MerchantActivity.title.ilike(f"%{keyword}%"),
                MerchantActivity.merchant_name.ilike(f"%{keyword}%"),
                MerchantActivity.product_name.ilike(f"%{keyword}%"),
            ),
        )
        .order_by(MerchantActivity.activity_price.asc().nullslast())
        .limit(100)
    )
    result = await db.execute(stmt)
    activities = [ActivityOut.model_validate(a) for a in result.scalars().all()]

    if not activities:
        return PriceComparisonResult(keyword=keyword, total_platforms=0, cheapest_platform=None, cheapest_price=None, items=[])

    priced = [a for a in activities if a.activity_price is not None and a.activity_price > 0]
    cheapest_price = min(a.activity_price for a in priced) if priced else None
    cheapest_platform = None
    if cheapest_price is not None:
        for a in priced:
            if a.activity_price == cheapest_price:
                cheapest_platform = a.platform
                break

    items = []
    for a in activities:
        items.append(
            PriceComparisonItem(
                platform=a.platform,
                platform_label=a.platform,
                activity_id=a.id,
                title=a.title,
                activity_price=a.activity_price,
                original_price=a.original_price,
                discount_description=a.discount_description,
                usage_conditions=a.usage_conditions,
                source_url=a.source_url,
                app_url=a.app_url,
                is_cheapest=(a.activity_price is not None and a.activity_price == cheapest_price),
            )
        )

    return PriceComparisonResult(
        keyword=keyword,
        total_platforms=len(set(a.platform for a in activities)),
        cheapest_platform=cheapest_platform,
        cheapest_price=cheapest_price,
        items=items,
    )


async def list_categories(db: AsyncSession) -> list[dict]:
    """返回当前有活跃活动的品类及数量。"""
    stmt = (
        select(
            MerchantActivity.category,
            func.count(MerchantActivity.id).label("count"),
        )
        .where(
            MerchantActivity.is_active == True,
            MerchantActivity.status == ActivityStatus.ACTIVE,
        )
        .group_by(MerchantActivity.category)
        .order_by(func.count(MerchantActivity.id).desc())
    )
    result = await db.execute(stmt)
    return [{"category": row.category, "count": row.count} for row in result.all()]


async def get_stats(db: AsyncSession) -> dict:
    """平台活动统计概览。"""
    stmt = (
        select(
            MerchantActivity.platform,
            func.count(MerchantActivity.id).label("count"),
        )
        .where(
            MerchantActivity.is_active == True,
            MerchantActivity.status == ActivityStatus.ACTIVE,
        )
        .group_by(MerchantActivity.platform)
        .order_by(func.count(MerchantActivity.id).desc())
    )
    result = await db.execute(stmt)
    platform_stats = {}
    total = 0
    for row in result.all():
        label = row.platform.value if hasattr(row.platform, "value") else str(row.platform)
        platform_stats[label] = row.count
        total += row.count

    # 分类统计
    cat_result = await db.execute(
        select(
            MerchantActivity.category,
            func.count(MerchantActivity.id).label("count"),
        )
        .where(
            MerchantActivity.is_active == True,
            MerchantActivity.status == ActivityStatus.ACTIVE,
        )
        .group_by(MerchantActivity.category)
    )
    categories = {row.category: row.count for row in cat_result.all()}

    return {
        "total_activities": total,
        "by_platform": platform_stats,
        "by_category": categories,
    }
