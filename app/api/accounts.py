"""账号 API：用户名+密码注册/登录/改密，支持跨设备跨域名找回数据。"""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_user_token, decode_token, generate_user_id, security
from app.database import get_db
from app.models.account import Account

router = APIRouter(prefix="/user", tags=["账号"])


# --- 密码工具 ---

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


# --- 请求模型 ---

class SignupRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32)
    password: str = Field(..., min_length=6, max_length=64)
    nickname: str = Field("", max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6, max_length=64)


def _account_info(acc: Account) -> dict:
    return {"username": acc.username, "nickname": acc.nickname or acc.username, "user_id": acc.user_id}


# --- 端点 ---

@router.post("/signup", summary="注册账号（自动绑定当前设备的数据）")
async def signup(
    body: SignupRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    username = body.username.strip()
    if await db.get(Account, username):
        raise HTTPException(400, "用户名已被注册")

    # 优先绑定当前令牌对应的 user_id（保留已有卡包数据）
    user_id = None
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials)
        if payload:
            user_id = payload.get("sub")
    if not user_id:
        user_id = generate_user_id()

    bound = (await db.execute(select(Account).where(Account.user_id == user_id))).scalar_one_or_none()
    if bound:
        raise HTTPException(400, "当前数据已绑定账号，请直接登录")

    salt = secrets.token_hex(16)
    acc = Account(
        username=username,
        password_hash=_hash_password(body.password, salt),
        salt=salt,
        user_id=user_id,
        nickname=(body.nickname or username),
    )
    db.add(acc)
    await db.commit()
    token = create_user_token(user_id, acc.nickname)
    return {"ok": True, "token": token, **_account_info(acc)}


@router.post("/login", summary="登录")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    acc = await db.get(Account, body.username.strip())
    if not acc or acc.password_hash != _hash_password(body.password, acc.salt):
        raise HTTPException(401, "用户名或密码错误")
    token = create_user_token(acc.user_id, acc.nickname or acc.username)
    return {"ok": True, "token": token, **_account_info(acc)}


@router.get("/account", summary="当前账号信息")
async def account_info(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    if not credentials or not credentials.credentials:
        return {"bound": False}
    payload = decode_token(credentials.credentials)
    if not payload:
        return {"bound": False}
    acc = (await db.execute(select(Account).where(Account.user_id == payload.get("sub")))).scalar_one_or_none()
    if not acc:
        return {"bound": False, "nickname": payload.get("nickname", "")}
    return {"bound": True, **_account_info(acc)}


@router.post("/change-password", summary="修改密码")
async def change_password(
    body: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    if not credentials or not credentials.credentials:
        raise HTTPException(401, "未登录")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(401, "登录已过期")
    acc = (await db.execute(select(Account).where(Account.user_id == payload.get("sub")))).scalar_one_or_none()
    if not acc:
        raise HTTPException(400, "当前未绑定账号")
    if acc.password_hash != _hash_password(body.old_password, acc.salt):
        raise HTTPException(401, "原密码错误")
    salt = secrets.token_hex(16)
    acc.salt = salt
    acc.password_hash = _hash_password(body.new_password, salt)
    await db.commit()
    return {"ok": True}
