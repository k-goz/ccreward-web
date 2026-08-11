"""JWT 认证工具：生成和验证 token，提供当前用户依赖注入。"""

import hashlib
import uuid
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)


def create_user_token(user_id: str, nickname: str = "用户") -> str:
    """为新用户创建 JWT，内含 user_id + 随机 salt。"""
    payload = {
        "sub": user_id,
        "nickname": nickname,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解码 JWT，失败返回 None。"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def generate_user_id() -> str:
    return f"u_{uuid.uuid4().hex[:16]}"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """严格认证：从 Authorization: Bearer <token> 提取当前用户。

    无有效 token 直接返回 401，不再自动创建匿名用户。
    生产环境必须通过 /api/user/register 或 /api/user/login 获取 token 后访问。
    """
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials)
        if payload:
            return {"user_id": payload["sub"], "nickname": payload.get("nickname", "用户"), "is_new": False}

    if settings.API_AUTH_ENFORCE:
        raise HTTPException(status_code=401, detail="请先登录")

    # 开发模式：自动创建匿名用户（API_AUTH_ENFORCE=false）
    user_id = generate_user_id()
    token = create_user_token(user_id, "访客")
    return {"user_id": user_id, "nickname": "访客", "is_new": True, "token": token}


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """可选认证：有 token 时返回用户信息，无 token 返回 None。

    用于公开读端点（如 cards 列表、activities 搜索），
    认证用户可获得个性化结果（搜索历史、我的银行筛选等），
    匿名用户仍可浏览公开内容。
    """
    if credentials and credentials.credentials:
        payload = decode_token(credentials.credentials)
        if payload:
            return {"user_id": payload["sub"], "nickname": payload.get("nickname", "用户"), "is_new": False}
    return None


async def require_account(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """严格认证：需要有效 token（用于需要账号绑定的端点）。

    与 get_current_user 相同行为，语义上用于需要账号的端点。
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    return {"user_id": payload["sub"], "nickname": payload.get("nickname", "用户"), "is_new": False}
