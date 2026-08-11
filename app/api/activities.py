from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_current_user_optional
from app.services import activity_service
from app.services.user_service import add_search_history
from app.models.activity import Platform
from app.schemas.activity import ActivityOut, PriceComparisonResult

router = APIRouter(prefix="/activities", tags=["商家活动"])


@router.get("", summary="搜索商家活动")
async def search_activities(
    keyword: str | None = Query(None, description="搜索关键词，如 瑞幸咖啡"),
    platform: Platform | None = Query(None, description="按平台筛选"),
    category: str | None = Query(None, description="按分类筛选"),
    sort: str = Query("updated", description="排序: updated / price"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_current_user_optional),
) -> dict:
    """搜索商家活动，支持分页 + 排序。认证用户会记录搜索历史。"""
    result = await activity_service.search_activities(
        db, keyword=keyword, platform=platform, category=category,
        sort=sort, page=page, page_size=page_size,
    )
    if keyword and user:
        await add_search_history(db, user["user_id"], keyword, result["total"])
    return result


@router.get("/compare", summary="多平台比价")
async def compare_prices(
    keyword: str = Query(..., description="比价关键词，如 瑞幸咖啡"),
    db: AsyncSession = Depends(get_db),
) -> PriceComparisonResult:
    return await activity_service.compare_prices(db, keyword=keyword)


@router.get("/categories", summary="活动品类列表")
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """返回当前有活跃活动的品类及数量。"""
    return await activity_service.list_categories(db)


@router.get("/stats", summary="活动统计概览")
async def activity_stats(db: AsyncSession = Depends(get_db)) -> dict:
    """返回各平台活动数量统计。"""
    return await activity_service.get_stats(db)
