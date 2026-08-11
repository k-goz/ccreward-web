"""用户 API：注册/登录、我的卡包、收藏、搜索历史。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_user_token, generate_user_id, get_current_user
from app.database import get_db
from app.services.user_service import (
    list_user_cards, add_user_card, update_user_card, remove_user_card,
    search_cards_for_add, list_banks,
    list_favorites, add_favorite, remove_favorite,
    list_search_history, add_search_history, clear_search_history,
)
from app.services.auth_service import wechat_login, firebase_login

router = APIRouter(prefix="/user", tags=["用户"])


# --- 请求模型 ---

class AddCardRequest(BaseModel):
    card_id: str | None = Field(None, description="种子库卡片ID（自定义卡可空）")
    nickname: str | None = Field(None, max_length=128)
    last_four: str | None = Field(None, max_length=4, description="卡号后四位")
    credit_limit: float | None = Field(None, description="额度（元）")
    issue_date: str | None = Field(None, description="办卡日期 YYYY-MM")
    expire_date: str | None = Field(None, description="到期月 YYYY-MM")
    annual_fee_condition: str | None = Field(None, max_length=256)
    annual_fee_waived: bool | None = Field(None)
    notes: str | None = Field(None)
    sort_order: int = Field(0)


class UpdateCardRequest(BaseModel):
    nickname: str | None = Field(None, max_length=128)
    last_four: str | None = Field(None, max_length=4)
    credit_limit: float | None = Field(None)
    issue_date: str | None = Field(None)
    expire_date: str | None = Field(None)
    annual_fee_condition: str | None = Field(None, max_length=256)
    annual_fee_waived: bool | None = Field(None)
    notes: str | None = Field(None)
    sort_order: int | None = Field(None)
    is_active: bool | None = Field(None)


class WeChatLoginRequest(BaseModel):
    code: str = Field(...)


class FirebaseLoginRequest(BaseModel):
    id_token: str = Field(...)


# --- 注册/登录 ---

@router.post("/register", summary="注册/获取 Token")
async def register():
    user_id = generate_user_id()
    token = create_user_token(user_id, "新用户")
    return {"user_id": user_id, "token": token, "nickname": "新用户"}


@router.get("/me", summary="当前用户信息")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/login/wechat", summary="微信小程序登录")
async def login_wechat(body: WeChatLoginRequest):
    return await wechat_login(body.code)


@router.post("/login/firebase", summary="Firebase 登录")
async def login_firebase(body: FirebaseLoginRequest):
    return await firebase_login(body.id_token)


# --- 我的卡包 ---

@router.get("/cards", summary="我的卡包")
async def my_cards(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """返回用户持有的所有卡片，含种子库权益信息。"""
    return await list_user_cards(db, user["user_id"])


@router.post("/cards", summary="添加卡片到卡包")
async def add_card(
    body: AddCardRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump()
    card_id = data.pop('card_id', '') or ''
    result = await add_user_card(db, user["user_id"], card_id, **data)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "添加失败"))
    return result


# --- 卡片搜索（添加时选卡，放在 {user_card_id} 路由前避免被拦截） ---

@router.get("/cards/search", summary="搜索种子库卡片")
async def search_cards(
    keyword: str = Query("", description="按卡名/银行搜索"),
    bank: str = Query("", description="按银行筛选"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """搜索种子库卡片，供添加到卡包时选择。"""
    return await search_cards_for_add(db, keyword, bank)


@router.get("/cards/banks", summary="种子库银行列表")
async def get_banks(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_banks(db)


@router.patch("/cards/{user_card_id}", summary="更新卡包中的卡片信息")
async def update_card(
    user_card_id: str,
    body: UpdateCardRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await update_user_card(db, user["user_id"], user_card_id, **body.model_dump(exclude_none=True))
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error", "未找到"))
    return result


@router.delete("/cards/{user_card_id}", summary="从卡包删除卡片")
async def delete_card(
    user_card_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await remove_user_card(db, user["user_id"], user_card_id)
    return {"ok": True}


# --- 收藏 ---

@router.get("/favorites", summary="我的收藏")
async def my_favorites(
    target_type: str = Query("activity"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_favorites(db, user["user_id"], target_type, page, page_size)


@router.post("/favorites", summary="添加收藏")
async def add_my_favorite(
    target_id: str = Query(...),
    target_type: str = Query("activity"),
    target_title: str = Query(""),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await add_favorite(db, user["user_id"], target_id, target_type, target_title)


@router.delete("/favorites/{target_id}", summary="取消收藏")
async def remove_my_favorite(
    target_id: str,
    target_type: str = Query("activity"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await remove_favorite(db, user["user_id"], target_id, target_type)
    return {"ok": True}


# --- 搜索历史 ---

@router.get("/search-history", summary="搜索历史")
async def my_search_history(
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await list_search_history(db, user["user_id"], limit)
    return {"items": items, "total": len(items)}


@router.delete("/search-history", summary="清除搜索历史")
async def clear_my_search_history(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await clear_search_history(db, user["user_id"])
    return {"ok": True}


# --- OCR 识别 ---

from fastapi import UploadFile, File
from app.services.baidu_ocr_service import recognize_card

@router.post("/cards/ocr", summary="拍照识别信用卡")
async def ocr_card(file: UploadFile = File(..., description="信用卡照片")):
    """上传信用卡照片，OCR 识别卡号、有效期、银行等信息。"""
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "请上传图片文件")
    
    image_bytes = await file.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "图片不能超过 10MB")
    
    result = await recognize_card(image_bytes)
    if "error" in result:
        raise HTTPException(500, result["error"])
    
    return result
