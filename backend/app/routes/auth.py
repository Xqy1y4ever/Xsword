"""登录 / 登出 / 会话。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..config import Settings
from ..deps import get_settings
from ..schemas import LoginIn
from ..security import (
    COOKIE_NAME,
    LoginLimiter,
    client_ip,
    make_session,
    verify_password,
    verify_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, settings: Settings = Depends(get_settings)):
    limiter: LoginLimiter = request.app.state.limiter
    ip = client_ip(request)
    if not limiter.allowed(ip):
        raise HTTPException(
            status_code=429,
            detail={"error": "too_many_attempts", "message": "尝试次数过多，请 15 分钟后再试"},
        )
    if not settings.admin_password_hash:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "password_not_set",
                "message": "服务端未设置口令，请先运行 npm run set-password 并写入 .env",
            },
        )
    if not verify_password(payload.password, settings.admin_password_hash):
        limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail={"error": "bad_password", "message": "口令不正确"})
    limiter.reset(ip)
    token = make_session(settings.session_secret, settings.session_ttl_days)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return {"ok": True, "authenticated": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True, "authenticated": False}


@router.get("/me")
def me(request: Request, settings: Settings = Depends(get_settings)):
    token = request.cookies.get(COOKIE_NAME, "")
    body = verify_session(settings.session_secret, token)
    return {"authenticated": body is not None}
