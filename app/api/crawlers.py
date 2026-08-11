"""爬虫管理 API：查询状态、历史、手动触发。"""

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.crawlers.scheduler import get_crawl_jobs, get_crawler_status, run_single_crawler

router = APIRouter(prefix="/crawlers", tags=["爬虫管理"])


@router.get("/status", summary="爬虫状态概览")
async def status():
    """获取所有爬虫最近一次执行的状态。"""
    return await get_crawler_status()


@router.get("/jobs", summary="爬虫任务历史")
async def jobs(limit: int = Query(20, ge=1, le=100)):
    """查询最近 N 条爬虫执行记录。"""
    return await get_crawl_jobs(limit=limit)


@router.post("/{crawler_name}/run", summary="手动触发爬虫")
async def trigger(
    crawler_name: str,
    user: dict = Depends(get_current_user),
):
    """手动立即执行指定爬虫（douyin / meituan）。需认证。"""
    return await run_single_crawler(crawler_name)
