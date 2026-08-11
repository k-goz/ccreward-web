"""数据导出 API — JSON 和 CSV 导出。"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.services.export_service import export_user_data, export_csv

router = APIRouter(prefix="/export", tags=["数据导出"])


@router.get("/json", summary="导出 JSON")
async def export_json(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """导出用户所有数据（卡包/权益/兑换/使用记录）为 JSON。"""
    return await export_user_data(user["user_id"], db, format="json")


@router.get("/csv", summary="导出 CSV")
async def export_csv_endpoint(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出用户卡包和权益使用记录为 CSV 文本。"""
    csv_data = await export_csv(user["user_id"], db)
    combined = f"=== cards.csv ===\n{csv_data['cards.csv']}\n\n=== expenses.csv ===\n{csv_data['expenses.csv']}"
    return PlainTextResponse(content=combined, media_type="text/plain; charset=utf-8")
