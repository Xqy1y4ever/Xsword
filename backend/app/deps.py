"""请求依赖。"""
from __future__ import annotations

from fastapi import Request

from .config import Settings
from .db import ConnectionProxy
from .security import require_auth


def get_conn(request: Request) -> ConnectionProxy:
    """返回惰性连接代理：真正执行 SQL 时才在接口所在线程取连接。"""
    return request.app.state.db.proxy()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def auth(request: Request) -> dict:
    return require_auth(request)
