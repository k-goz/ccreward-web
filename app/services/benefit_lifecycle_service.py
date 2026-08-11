"""信用卡权益生命周期巡检服务：对比种子数据发现变更，自动标记过期，PushPlus 推送。"""
import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, DATA_DIR
from app.database import async_session
from app.models.benefit import CardBenefit
from app.services.notification_service import send_notification

logger = logging.getLogger(__name__)

_INSPECTION_FILE = DATA_DIR / "benefit_inspection.json"


def _load_last_report() -> dict | None:
    """从文件加载上一次权益巡检报告。"""
    try:
        if _INSPECTION_FILE.exists():
            return json.loads(_INSPECTION_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取权益巡检报告失败: {e}")
    return None


def _save_report(report: dict) -> None:
    """将权益巡检报告保存到文件。"""
    try:
        _INSPECTION_FILE.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"保存权益巡检报告失败: {e}")


async def inspect_benefits(db: AsyncSession) -> dict:
    """巡检所有 CardBenefit：过期标记 + 种子差异对比 + 语义变更检测。

    规则：
    1. 有 valid_to 且 valid_to < now → 标记 is_active=False
    2. 种子有、DB 无 → 新权益（seed upsert 下次会自动导入，此处记录）
    3. DB 有、种子无 → 可能银行已取消，标记 is_active=False
    4. id 相同但关键字段变化 → 语义变更，记录 diff
    """
    now = datetime.now()

    # Step 1: 查询所有活跃权益
    result_all = await db.execute(select(CardBenefit).where(CardBenefit.is_active == True))
    active_benefits = result_all.scalars().all()

    # Step 2: 过期标记（valid_to < now）
    expired_ids: list[str] = []
    for b in active_benefits:
        if b.valid_to is not None and b.valid_to < now:
            b.is_active = False
            expired_ids.append(b.id)
            logger.info(f"[权益巡检] 标记过期: {b.id} ({b.title}) valid_to={b.valid_to}")

    # 重新查询 active（排除刚标记过期的）
    result_active = await db.execute(select(CardBenefit).where(CardBenefit.is_active == True))
    active_benefits = result_active.scalars().all()

    # Step 3: 加载种子数据
    from app.seed_data.cards import BENEFITS as SEED_BENEFITS

    seed_ids = {b["id"] for b in SEED_BENEFITS}
    db_ids = {b.id for b in active_benefits}

    # 种子新增（DB 中不存在）
    new_in_seed = seed_ids - db_ids

    # 银行可能取消（DB 中存在但种子中已移除）
    removed_from_seed_ids = db_ids - seed_ids
    for bid in removed_from_seed_ids:
        b = await db.get(CardBenefit, bid)
        if b and b.is_active:
            b.is_active = False
            logger.info(f"[权益巡检] 种子已移除，标记过期: {bid} ({b.title})")

    # Step 4: 语义变更检测（id 相同但关键字段变化）
    changed = []
    both = seed_ids & db_ids
    key_fields = ["cashback_percent", "discount_percent", "points_per_yuan", "title", "description"]

    for bid in both:
        seed_b = next(b for b in SEED_BENEFITS if b["id"] == bid)
        db_b = next(b for b in active_benefits if b.id == bid)
        diffs = {}
        for field in key_fields:
            seed_val = seed_b.get(field)
            db_val = getattr(db_b, field, None)
            if seed_val != db_val:
                diffs[field] = {"seed": seed_val, "db": db_val}
        if diffs:
            # 种子值为准，更新 DB
            for field in key_fields:
                seed_val = seed_b.get(field)
                if seed_val is not None:
                    setattr(db_b, field, seed_val)
            changed.append({"id": bid, "title": db_b.title, "diffs": diffs})
            logger.info(f"[权益巡检] 字段变更: {bid} ({db_b.title}) -> {list(diffs.keys())}")

    await db.commit()

    report = {
        "inspection_time": now.isoformat(),
        "total_active_before": len(active_benefits) + len(expired_ids) + len(removed_from_seed_ids),
        "newly_expired_by_valid_to": len(expired_ids),
        "newly_expired_by_valid_to_items": expired_ids,
        "new_in_seed": len(new_in_seed),
        "new_in_seed_items": sorted(list(new_in_seed)),
        "removed_from_seed": len(removed_from_seed_ids),
        "removed_from_seed_items": sorted(list(removed_from_seed_ids)),
        "semantic_changes": len(changed),
        "semantic_changes_items": changed,
        "kept_active": len(active_benefits),
        "suggested_actions": _build_benefit_suggestions(
            expired_ids, new_in_seed, removed_from_seed_ids, changed
        ),
    }

    _save_report(report)
    logger.info(
        f"[权益巡检] 过期{len(expired_ids)}, 种子新增{len(new_in_seed)}, "
        f"种子移除{len(removed_from_seed_ids)}, 变更{len(changed)}, "
        f"活跃{len(active_benefits)}"
    )
    return report


def _build_benefit_suggestions(
    expired_ids: list[str],
    new_in_seed: set[str],
    removed_from_seed: set[str],
    changed: list[dict],
) -> list[str]:
    """生成权益巡检建议操作列表。"""
    suggestions = []
    if expired_ids:
        suggestions.append(f"{len(expired_ids)} 条权益因 valid_to 过期已自动标记失效")
    if new_in_seed:
        suggestions.append(
            f"{len(new_in_seed)} 条种子新增权益，下次 seed upsert 将自动导入"
        )
    if removed_from_seed:
        suggestions.append(
            f"{len(removed_from_seed)} 条权益在种子中已移除，已标记失效；若误判请回填种子数据"
        )
    if changed:
        field_names = set()
        for c in changed:
            field_names.update(c["diffs"].keys())
        suggestions.append(
            f"{len(changed)} 条权益字段变更（{'/'.join(sorted(field_names))}），已以种子为准更新 DB"
        )
    if not suggestions:
        suggestions.append("所有权益状态正常，无变更")
    return suggestions


async def get_inspection_report() -> dict:
    """获取最近一次权益巡检报告（从文件读取）。"""
    report = _load_last_report()
    if report:
        return report
    return {
        "inspection_time": None,
        "total_active_before": 0,
        "newly_expired_by_valid_to": 0,
        "newly_expired_by_valid_to_items": [],
        "new_in_seed": 0,
        "new_in_seed_items": [],
        "removed_from_seed": 0,
        "removed_from_seed_items": [],
        "semantic_changes": 0,
        "semantic_changes_items": [],
        "kept_active": 0,
        "suggested_actions": ["尚未执行权益巡检"],
    }


async def run_inspection_and_notify() -> None:
    """在 APScheduler / 手动触发中调用：执行权益巡检并通过通知系统推送结果。"""
    logger.info("=== 权益巡检开始 ===")
    try:
        async with async_session() as db:
            report = await inspect_benefits(db)

        # 构建推送消息
        title = f"🔍 权益巡检报告 ({datetime.now().strftime('%m/%d')})"
        lines = []
        # 有变更时才推详细
        has_changes = (
            report["newly_expired_by_valid_to"]
            or report["new_in_seed"]
            or report["removed_from_seed"]
            or report["semantic_changes"]
        )
        if has_changes:
            lines.append(f"权益巡检结果：")
            lines.append(f"  - 过期失效: {report['newly_expired_by_valid_to']} 条")
            lines.append(f"  - 种子新增: {report['new_in_seed']} 条")
            lines.append(f"  - 种子移除: {report['removed_from_seed']} 条")
            lines.append(f"  - 字段变更: {report['semantic_changes']} 条")
            lines.append(f"  - 保持活跃: {report['kept_active']} 条")
            lines.append("")

            if report["newly_expired_by_valid_to"]:
                lines.append("过期失效明细：")
                for oid in report["newly_expired_by_valid_to_items"]:
                    lines.append(f"  - {oid}")
                lines.append("")

            if report["removed_from_seed"]:
                lines.append("种子移除明细：")
                for oid in report["removed_from_seed_items"]:
                    lines.append(f"  - {oid}")
                lines.append("")

            if report["semantic_changes"]:
                lines.append("字段变更明细：")
                for c in report["semantic_changes_items"]:
                    fields = "/".join(c["diffs"].keys())
                    lines.append(f"  - {c['id']} ({c['title']}): {fields}")
                lines.append("")
        else:
            lines.append(
                f"权益巡检: 全部 {report['kept_active']} 条权益均正常，无变更"
            )
            lines.append("")

        if report["suggested_actions"]:
            lines.append("建议操作：")
            for s in report["suggested_actions"]:
                lines.append(f"  - {s}")

        await send_notification(title, "\n".join(lines))
        logger.info("=== 权益巡检完成 ===")
    except Exception as e:
        logger.error(f"权益巡检异常: {e}", exc_info=True)
