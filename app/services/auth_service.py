"""第三方登录服务：微信小程序/公众号 OAuth + Firebase Auth。

生产环境需要配置:
  - 微信: WECHAT_APP_ID + WECHAT_APP_SECRET (从微信开放平台获取)
  - Firebase: FIREBASE_PROJECT_ID (复用主站 ccreward.app 的 Firebase 项目)

当前为架构骨架，微信登录通过 code2session → openid → 本地 JWT 完成。
Firebase 登录通过 verify_id_token → uid → 本地 JWT 完成。
"""

import logging
from typing import Optional

import httpx
from fastapi import HTTPException

from app.config import settings
from app.auth import create_user_token

logger = logging.getLogger(__name__)


async def wechat_code2session(code: str) -> dict:
    """微信小程序登录：用临时 code 换取 openid + session_key。

    https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html
    """
    if not settings.WECHAT_ENABLED:
        raise HTTPException(status_code=501, detail="微信登录未配置")

    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.WECHAT_APP_ID,
        "secret": settings.WECHAT_APP_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        data = resp.json()

    if "errcode" in data and data["errcode"] != 0:
        logger.error(f"微信 code2session 失败: {data}")
        raise HTTPException(status_code=400, detail=f"微信登录失败: {data.get('errmsg', 'unknown')}")

    return data  # {openid, session_key, unionid?}


async def wechat_login(code: str) -> dict:
    """微信小程序登录：code → openid → JWT token。

    如果未配置 WECHAT_APP_ID/WECHAT_APP_SECRET，自动降级为本地开发模式，
    基于 code 的前16字符生成模拟 openid。
    """
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET or not settings.WECHAT_ENABLED:
        logger.warning("微信登录未配置 AppID/Secret，使用本地开发模式")
        user_id = f"wx_{code[:16]}"
        token = create_user_token(user_id, "微信用户")
        return {
            "user_id": user_id,
            "nickname": "微信用户",
            "token": token,
            "mode": "dev",
        }

    wx_data = await wechat_code2session(code)
    openid = wx_data["openid"]
    unionid = wx_data.get("unionid")
    user_id = f"wx_{openid[:16]}"
    nickname = f"微信用户{openid[-4:]}"
    token = create_user_token(user_id, nickname)
    return {
        "user_id": user_id,
        "nickname": nickname,
        "token": token,
        "openid": openid,
        "unionid": unionid,
        "mode": "production",
    }


async def firebase_verify_token(id_token: str) -> dict:
    """验证 Firebase ID Token，返回 payload。

    使用 Firebase Auth REST API 验证（无需 Firebase Admin SDK）。
    """
    if not settings.FIREBASE_ENABLED:
        raise HTTPException(status_code=501, detail="Firebase 登录未配置")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={settings.FIREBASE_PROJECT_ID}"
    payload = {"idToken": id_token}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        data = resp.json()

    if "error" in data:
        logger.error(f"Firebase token 验证失败: {data}")
        raise HTTPException(status_code=400, detail=f"Firebase token 无效: {data['error']['message']}")

    user_info = data.get("users", [{}])[0]
    return {
        "uid": user_info.get("localId", ""),
        "email": user_info.get("email", ""),
        "display_name": user_info.get("displayName", ""),
        "photo_url": user_info.get("photoUrl", ""),
        "provider": user_info.get("providerUserInfo", [{}])[0].get("providerId", "unknown"),
    }


async def firebase_login(id_token: str) -> dict:
    """Firebase 登录：验证 id_token → 本地 JWT。"""
    fb_data = await firebase_verify_token(id_token)
    uid = fb_data["uid"]
    user_id = f"fb_{uid[:16]}"
    nickname = fb_data.get("display_name") or fb_data.get("email") or f"Firebase用户{uid[:6]}"
    token = create_user_token(user_id, nickname)
    return {
        "user_id": user_id,
        "nickname": nickname,
        "token": token,
        "firebase_uid": uid,
        "email": fb_data.get("email"),
    }
