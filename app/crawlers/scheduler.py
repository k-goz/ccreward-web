"""爬虫统一调度器：管理所有爬虫实例，支持定时和手动触发。"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import desc, select, func, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.activity import MerchantActivity, ActivityStatus
from app.models.crawl_job import CrawlJob, CrawlStatus

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def _get_all_crawlers():
    """延迟导入，避免循环依赖。"""
    from app.crawlers.douyin import DouyinCrawler
    from app.crawlers.meituan import MeituanCrawler
    from app.crawlers.jd import JDCrawler, JDGroceryCrawler
    from app.crawlers.smzdm import SMZDMCrawler
    return [DouyinCrawler(), MeituanCrawler(), JDCrawler(), JDGroceryCrawler(), SMZDMCrawler()]


async def run_single_crawler(crawler_name: str) -> dict:
    """手动触发单个爬虫。"""
    crawlers = _get_all_crawlers()
    target = next((c for c in crawlers if c.name == crawler_name), None)
    if not target:
        return {"success": False, "error": f"未找到爬虫: {crawler_name}"}
    async with async_session() as db:
        saved = await target.run(db)
    return {"success": True, "crawler": crawler_name, "saved": saved}


async def _cleanup_stale_activities(db: AsyncSession, retention_days: int = 90) -> int:
    """清理过期活动：valid_to 超过 retention_days 天的标记为过期。"""
    cutoff = datetime.now() - timedelta(days=retention_days)
    result = await db.execute(
        select(MerchantActivity).where(
            MerchantActivity.valid_to < cutoff,
            MerchantActivity.status == ActivityStatus.ACTIVE,
        )
    )
    stale = result.scalars().all()
    count = len(stale)
    for act in stale:
        act.status = ActivityStatus.EXPIRED
    if count:
        await db.commit()
        logger.info(f"清理过期活动: {count} 条")
    return count


async def _deduplicate_activities(db: AsyncSession) -> int:
    """去重：同一平台+同一商家+相似标题的活动只保留最新。"""
    # 按 merchant_name + platform 查找重复
    result = await db.execute(
        select(
            MerchantActivity.merchant_name,
            MerchantActivity.platform,
            func.count(MerchantActivity.id).label("cnt"),
        )
        .where(MerchantActivity.status == ActivityStatus.ACTIVE)
        .group_by(MerchantActivity.merchant_name, MerchantActivity.platform)
        .having(func.count(MerchantActivity.id) > 3)
    )
    dupes = result.all()
    removed = 0
    for row in dupes:
        # 保留最新的 3 条，其余标为 expired
        subq = await db.execute(
            select(MerchantActivity)
            .where(
                MerchantActivity.merchant_name == row.merchant_name,
                MerchantActivity.platform == row.platform,
                MerchantActivity.status == ActivityStatus.ACTIVE,
            )
            .order_by(desc(MerchantActivity.updated_at))
            .offset(3)
        )
        to_expire = subq.scalars().all()
        for a in to_expire:
            a.status = ActivityStatus.EXPIRED
            removed += 1
    if removed:
        await db.commit()
        logger.info(f"去重: 清理 {removed} 条重复活动")
    return removed


async def run_all_crawlers() -> None:
    """执行所有爬虫（供定时器调用），附带清理和去重。"""
    from app.config import settings
    if not settings.CRAWLER_ENABLED:
        logger.info("爬虫已禁用 (CRAWLER_ENABLED=false)")
        return
    logger.info("=== 定时爬取任务开始 ===")
    crawlers = _get_all_crawlers()
    async with async_session() as db:
        for crawler in crawlers:
            try:
                await crawler.run(db)
            except Exception as e:
                logger.error(f"[{crawler.name}] 执行异常: {e}", exc_info=True)

        # 爬取完成后做增量维护
        try:
            expired = await _cleanup_stale_activities(db)
            removed = await _deduplicate_activities(db)
            logger.info(f"增量维护: 过期 {expired}, 去重 {removed}")
        except Exception as e:
            logger.error(f"增量维护异常: {e}", exc_info=True)

    logger.info("=== 定时爬取任务完成 ===")


async def get_crawl_jobs(limit: int = 20) -> list[dict]:
    """查询最近的爬虫任务记录。"""
    async with async_session() as db:
        result = await db.execute(
            select(CrawlJob).order_by(desc(CrawlJob.started_at)).limit(limit)
        )
        jobs = result.scalars().all()
        return [
            {
                "id": j.id,
                "crawler_name": j.crawler_name,
                "platform": j.platform,
                "status": j.status.value,
                "items_fetched": j.items_fetched,
                "items_saved": j.items_saved,
                "items_new": j.items_new,
                "items_updated": j.items_updated,
                "duration_seconds": j.duration_seconds,
                "error_message": j.error_message,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in jobs
        ]


async def get_crawler_status() -> list[dict]:
    """获取所有爬虫最近执行状态。"""
    async with async_session() as db:
        # 每个爬虫最近一次任务
        subq = (
            select(
                CrawlJob.crawler_name,
                func.max(CrawlJob.started_at).label("max_started"),
            )
            .group_by(CrawlJob.crawler_name)
            .subquery()
        )
        result = await db.execute(
            select(CrawlJob).join(
                subq,
                (CrawlJob.crawler_name == subq.c.crawler_name)
                & (CrawlJob.started_at == subq.c.max_started),
            )
        )
        jobs = result.scalars().all()
        return [
            {
                "crawler_name": j.crawler_name,
                "platform": j.platform,
                "last_status": j.status.value,
                "last_run": j.started_at.isoformat() if j.started_at else None,
                "last_saved": j.items_saved,
                "last_new": j.items_new,
                "last_error": j.error_message,
            }
            for j in jobs
        ]


def start_scheduler() -> None:
    from app.config import settings
    scheduler = get_scheduler()
    scheduler.add_job(
        run_all_crawlers,
        "interval",
        hours=settings.CRAWLER_INTERVAL_HOURS,
        id="crawl_all",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
        logger.info(f"爬虫调度器已启动，间隔 {settings.CRAWLER_INTERVAL_HOURS} 小时")


def stop_scheduler() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown()
        logger.info("爬虫调度器已停止")
