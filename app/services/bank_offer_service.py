"""银行优惠巡检服务：每周检查优惠时效性，自动标记过期与清理。"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, DATA_DIR
from app.database import async_session
from app.models.bank_offer import BankOffer, OfferStatus
from app.services.notification_service import send_notification

logger = logging.getLogger(__name__)

_INSPECTION_FILE = DATA_DIR / "bank_offer_inspection.json"


def _load_last_report() -> dict | None:
    """从文件加载上一次巡检报告。"""
    try:
        if _INSPECTION_FILE.exists():
            return json.loads(_INSPECTION_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取巡检报告失败: {e}")
    return None


def _save_report(report: dict) -> None:
    """将巡检报告保存到文件。"""
    try:
        _INSPECTION_FILE.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"保存巡检报告失败: {e}")


async def inspect_bank_offers(db: AsyncSession) -> dict:
    """巡检所有 bank_offers，标记过期，清理陈旧数据，返回报告。

    规则：
    1. valid_to 已过期 → 标记 EXPIRED + is_active=False
    2. valid_to 为 None 但有 valid_period 文字 → 需人工确认（不自动标记）
    3. 已过期超过 30 天的 → 从 DB 删除（下次 seed upsert 可以添加回来）
    """
    now = datetime.now()
    expired_ids: list[str] = []
    newly_expired: list[str] = []
    need_review: list[str] = []
    deleted_ids: list[str] = []
    kept_active: int = 0

    # 查询所有活跃的 offer
    result = await db.execute(select(BankOffer).where(BankOffer.is_active == True))
    offers = result.scalars().all()

    for offer in offers:
        is_expired = False
        need_manual = False

        if offer.valid_to is not None:
            if offer.valid_to < now:
                is_expired = True
            else:
                kept_active += 1
                continue
        else:
            # valid_to 为空，但可能有 valid_period 文本
            if offer.valid_period and offer.valid_period.strip():
                # 有文字但没有具体日期 → 需人工确认
                need_review.append(offer.id)
                # 已经标记为 EXPIRED 的才处理，ACTIVE/REGULAR 保留
                if offer.status == OfferStatus.EXPIRED:
                    # 之前就标了 EXPIRED 但 valid_to 为空 → 保留 EXPIRED 状态
                    expired_ids.append(offer.id)
                else:
                    kept_active += 1
                    continue
            else:
                # 没有 valid_to 也没有 valid_period → 保留原状态
                kept_active += 1
                continue

        if is_expired or offer.status == OfferStatus.EXPIRED:
            # 标记为过期
            if offer.status != OfferStatus.EXPIRED:
                newly_expired.append(offer.id)
                offer.status = OfferStatus.EXPIRED
            offer.is_active = False
            expired_ids.append(offer.id)

    # 处理已过期超过 30 天的 → 删除
    cutoff = now - timedelta(days=30)
    result_stale = await db.execute(
        select(BankOffer).where(
            BankOffer.status == OfferStatus.EXPIRED,
            BankOffer.is_active == False,
            BankOffer.valid_to < cutoff,
        )
    )
    stale_offers = result_stale.scalars().all()
    for offer in stale_offers:
        deleted_ids.append(offer.id)
        await db.delete(offer)

    await db.commit()

    report = {
        "inspection_time": now.isoformat(),
        "total_active_before": len(offers),
        "newly_expired": len(newly_expired),
        "newly_expired_items": newly_expired,
        "total_expired": len(expired_ids),
        "need_manual_review": len(need_review),
        "need_manual_review_items": need_review,
        "deleted_stale": len(deleted_ids),
        "deleted_stale_items": deleted_ids,
        "kept_active": kept_active,
        "suggested_actions": _build_suggestions(newly_expired, need_review, deleted_ids),
    }

    _save_report(report)
    logger.info(
        f"[银行优惠巡检] 新过期 {len(newly_expired)}, "
        f"需人工 {len(need_review)}, 删除陈旧 {len(deleted_ids)}, "
        f"保持活跃 {kept_active}"
    )
    return report


def _build_suggestions(
    newly_expired: list[str],
    need_review: list[str],
    deleted_ids: list[str],
) -> list[str]:
    """生成建议操作列表。"""
    suggestions = []
    if newly_expired:
        suggestions.append(
            f"{len(newly_expired)} 条优惠已自动标记过期，建议从 seed_data 中移除或更新 valid_to 后重新导入"
        )
    if need_review:
        suggestions.append(
            f"{len(need_review)} 条优惠无明确过期日期，需人工确认是否仍有效"
        )
    if deleted_ids:
        suggestions.append(
            f"{len(deleted_ids)} 条过期超30天的陈旧数据已从数据库删除"
        )
    if not suggestions:
        suggestions.append("所有优惠均未过期，无需操作")
    return suggestions


async def get_inspection_report(db: AsyncSession | None = None) -> dict:
    """获取最近一次巡检报告（从文件读取）。"""
    report = _load_last_report()
    if report:
        return report
    return {
        "inspection_time": None,
        "total_active_before": 0,
        "newly_expired": 0,
        "newly_expired_items": [],
        "total_expired": 0,
        "need_manual_review": 0,
        "need_manual_review_items": [],
        "deleted_stale": 0,
        "deleted_stale_items": [],
        "kept_active": 0,
        "suggested_actions": ["尚未执行巡检"],
    }


async def run_inspection_and_notify() -> None:
    """在 APScheduler 中被调用：执行巡检并通过通知系统推送结果。"""
    logger.info("=== 银行优惠周巡检开始 ===")
    try:
        async with async_session() as db:
            report = await inspect_bank_offers(db)

        # 构建推送消息
        title = f"🏦 银行优惠巡检 ({datetime.now().strftime('%m/%d')})"
        lines = [
            f"本周巡检结果：",
            f"  - 新过期：{report['newly_expired']} 条",
            f"  - 需人工确认：{report['need_manual_review']} 条",
            f"  - 已清理陈旧：{report['deleted_stale']} 条",
            f"  - 保持活跃：{report['kept_active']} 条",
            f"",
        ]
        if report["newly_expired"]:
            lines.append("新过期明细：")
            for oid in report["newly_expired_items"]:
                lines.append(f"  - {oid}")
            lines.append("")
        if report["need_manual_review"]:
            lines.append("需人工确认：")
            for oid in report["need_manual_review_items"]:
                lines.append(f"  - {oid}")
            lines.append("")
        if report["suggested_actions"]:
            lines.append("建议操作：")
            for s in report["suggested_actions"]:
                lines.append(f"  - {s}")

        await send_notification(title, "\n".join(lines))
        logger.info("=== 银行优惠周巡检完成 ===")
    except Exception as e:
        logger.error(f"银行优惠巡检异常: {e}", exc_info=True)
