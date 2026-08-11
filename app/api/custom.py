"""自定义权益与兑换 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.services.custom_benefit_service import (
    merge_benefits,
    upsert_benefit_override,
    delete_benefit_override,
    add_redemption,
    get_card_redemptions_full,
    delete_redemption_override,
)

router = APIRouter(prefix="/custom", tags=["自定义权益"])


# ────────────────────────────────────────
# 请求模型
# ────────────────────────────────────────

class BenefitOverrideRequest(BaseModel):
    user_card_id: str = Field(...)
    card_id: str | None = Field(None)
    benefit_id: str | None = Field(None, description="若要覆盖已有权益则提供")
    title: str | None = Field(None, max_length=256)
    description: str | None = Field(None)
    benefit_type: str | None = Field(None, max_length=32)
    category: str | None = Field(None, max_length=32)
    discount_percent: float | None = Field(None)
    cashback_percent: float | None = Field(None)
    points_per_yuan: float | None = Field(None)
    value_text: str | None = Field(None, max_length=128)
    usage_limit: str | None = Field(None, max_length=256)
    merchant_tags: str | None = Field(None)
    effective_from: str | None = Field(None, description="YYYY-MM-DD")
    effective_to: str | None = Field(None, description="YYYY-MM-DD")
    notes: str | None = Field(None)


class RedemptionOverrideRequest(BaseModel):
    user_card_id: str = Field(...)
    card_id: str | None = Field(None)
    item_name: str = Field(..., max_length=256)
    merchant_name: str | None = Field(None, max_length=128)
    category: str | None = Field(None, max_length=64)
    points_required: float = Field(...)
    cash_value: float | None = Field(None)
    description: str | None = Field(None)
    notes: str | None = Field(None)


# ────────────────────────────────────────
# 权益覆盖
# ────────────────────────────────────────

@router.get("/benefits/{user_card_id}", summary="某卡完整权益（合并后）")
async def get_card_benefits(
    user_card_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回种子权益 + 用户覆盖合并后的完整权益列表。"""
    return await merge_benefits(user_card_id, db)


@router.post("/benefits", summary="新增/覆盖权益")
async def create_or_update_benefit(
    body: BenefitOverrideRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """创建新覆盖或更新已有覆盖。

    - 若提供 benefit_id 且已存在覆盖 → 更新
    - 否则 → 新建覆盖或新增额外权益
    """
    data = body.model_dump(exclude_none=False)

    # 转换日期字符串
    for date_field in ["effective_from", "effective_to"]:
        if data.get(date_field):
            from datetime import date as dt_date
            try:
                data[date_field] = dt_date.fromisoformat(data[date_field])
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail=f"日期格式错误：{date_field}")

    return await upsert_benefit_override(data, user["user_id"], db)


@router.delete("/benefits/{override_id}", summary="删除覆盖")
async def remove_benefit_override(
    override_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await delete_benefit_override(override_id, db)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "删除失败"))
    return result


# ────────────────────────────────────────
# 自定义兑换
# ────────────────────────────────────────

@router.get("/redemptions/{card_id}", summary="某卡完整兑换（含自定义）")
async def get_redemptions(
    card_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """返回种子兑换 + 用户自定义兑换的完整列表。"""
    return await get_card_redemptions_full(card_id, user["user_id"], db)


@router.post("/redemptions", summary="新增自定义兑换")
async def create_redemption(
    body: RedemptionOverrideRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = body.model_dump()
    return await add_redemption(data, user["user_id"], db)


@router.delete("/redemptions/{override_id}", summary="删除自定义兑换")
async def remove_redemption(
    override_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await delete_redemption_override(override_id, db)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "删除失败"))
    return result
