"""爬虫基类：重试、限速、任务追踪、数据校验。

子类只需实现 fetch() 返回待入库字典列表，其余由基类统一处理。
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.models.activity import MerchantActivity, ActivityStatus, Platform
from app.models.crawl_job import CrawlJob, CrawlStatus

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 5  # 秒
REQUEST_DELAY = 1.0  # 请求间隔
FETCH_TIMEOUT = 60  # 秒


class BaseCrawler(ABC):
    name: str = "base"
    platform: Platform = Platform.OTHER
    max_retries: int = MAX_RETRIES
    request_delay: float = REQUEST_DELAY

    @abstractmethod
    async def fetch(self) -> list[dict]:
        """抓取原始活动数据，返回待入库的字典列表。

        每个 dict 必须包含:
          - id: str         活动唯一ID（建议: {platform}_{merchant}_{item_hash}）
          - title: str      活动标题
          - platform: Platform
          - merchant_name: str
          - category: str
          - discount_description: str
          可选字段参考 MerchantActivity 模型。
        """
        ...

    def _build_id(self, *parts: str) -> str:
        """根据平台+商家+特征生成确定性 ID。"""
        import hashlib
        raw = "_".join(str(p) for p in parts)
        return f"crawl_{self.name}_{hashlib.md5(raw.encode()).hexdigest()[:12]}"

    def _validate_items(self, items: list[dict]) -> list[dict]:
        """校验抓取数据：补全缺失字段、过滤无效记录。"""
        valid = []
        for item in items:
            if not item.get("title") or not item.get("merchant_name"):
                logger.warning(f"[{self.name}] 跳过缺少标题/商家的数据: {item.get('id', 'N/A')}")
                continue
            item.setdefault("id", self._build_id(item.get("title", ""), item.get("merchant_name", "")))
            item.setdefault("platform", self.platform)
            item.setdefault("category", "餐饮美食")
            item.setdefault("discount_description", item.get("title", ""))
            item.setdefault("source_type", "crawler")
            item.setdefault("status", ActivityStatus.ACTIVE)
            item.setdefault("is_active", True)
            valid.append(item)
        return valid

    async def save(self, db: AsyncSession, items: list[dict]) -> dict[str, int]:
        """将抓取数据 upsert 入库，返回 {saved, new, updated}。"""
        new = updated = 0
        for item in items:
            activity_id = item["id"]
            existing = await db.get(MerchantActivity, activity_id)
            if existing:
                for key, value in item.items():
                    setattr(existing, key, value)
                existing.updated_at = datetime.now()
                updated += 1
            else:
                activity = MerchantActivity(**item)
                db.add(activity)
                new += 1
        await db.commit()
        return {"saved": new + updated, "new": new, "updated": updated}

    async def _create_job(self, db: AsyncSession) -> CrawlJob:
        job = CrawlJob(
            id=str(uuid.uuid4()),
            crawler_name=self.name,
            platform=str(self.platform.value),
            status=CrawlStatus.RUNNING,
        )
        db.add(job)
        await db.commit()
        return job

    async def _finish_job(
        self,
        db: AsyncSession,
        job: CrawlJob,
        status: CrawlStatus,
        stats: dict,
        error: str | None = None,
    ):
        stmt = (
            update(CrawlJob)
            .where(CrawlJob.id == job.id)
            .values(
                status=status,
                items_fetched=stats["fetched"],
                items_saved=stats.get("saved", 0),
                items_new=stats.get("new", 0),
                items_updated=stats.get("updated", 0),
                error_message=error,
                finished_at=datetime.now(),
            )
        )
        await db.execute(stmt)
        await db.commit()

    async def run(self, db: AsyncSession) -> int:
        """执行一次完整的抓取-保存流程（含重试），返回保存数量。"""
        job = await self._create_job(db)
        start = datetime.now()
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"[{self.name}] 第 {attempt}/{self.max_retries} 次尝试抓取")
                raw = await asyncio.wait_for(self.fetch(), timeout=FETCH_TIMEOUT)
                items = self._validate_items(raw)
                stats = await self.save(db, items)
                duration = (datetime.now() - start).total_seconds()

                status = CrawlStatus.SUCCESS if stats["new"] + stats["updated"] > 0 else CrawlStatus.SUCCESS
                await self._finish_job(
                    db, job, status,
                    {"fetched": len(raw), **stats},
                )
                # Also write duration
                await db.execute(
                    update(CrawlJob)
                    .where(CrawlJob.id == job.id)
                    .values(duration_seconds=duration)
                )
                await db.commit()

                logger.info(
                    f"[{self.name}] 完成: 抓取 {len(raw)} 条, "
                    f"新增 {stats['new']}, 更新 {stats['updated']}, "
                    f"耗时 {duration:.1f}s"
                )
                return stats["saved"]
            except asyncio.TimeoutError:
                last_error = f"超时 ({FETCH_TIMEOUT}s)"
                logger.warning(f"[{self.name}] {last_error}, 第 {attempt} 次失败")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[{self.name}] 第 {attempt} 次失败: {e}")
            if attempt < self.max_retries:
                await asyncio.sleep(RETRY_BACKOFF * attempt)

        duration = (datetime.now() - start).total_seconds()
        await self._finish_job(
            db, job, CrawlStatus.FAILED,
            {"fetched": 0, "saved": 0, "new": 0, "updated": 0},
            error=last_error,
        )
        await db.execute(
            update(CrawlJob)
            .where(CrawlJob.id == job.id)
            .values(duration_seconds=duration)
        )
        await db.commit()
        logger.error(f"[{self.name}] 全部 {self.max_retries} 次重试失败: {last_error}")
        return 0
