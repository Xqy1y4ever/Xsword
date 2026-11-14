"""FastAPI 应用装配。"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from . import llm_config
from .db import Database
from .routes import annotate, auth, cycle, llm, roots, stats, words
from .security import LoginLimiter

logger = logging.getLogger("vocab")

ROOT = Path(__file__).resolve().parents[2]

# index.html 永远不缓存，避免发版后浏览器拿旧 HTML 去请求已删除的哈希资源（会白屏）
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _no_cache(response):
    response.headers.update(NO_CACHE_HEADERS)
    return response


class ImmutableStaticFiles(StaticFiles):
    """构建产物带内容哈希，可以长缓存。"""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    if not settings.session_secret:
        settings.session_secret = secrets.token_hex(32)
        logger.warning("SESSION_SECRET 未配置，已使用临时密钥；重启后登录状态失效。")
    if not settings.admin_password_hash:
        logger.warning("ADMIN_PASSWORD_HASH 未配置，登录接口会返回 503；请运行 npm run set-password。")

    app = FastAPI(title="背单词", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.db = db or Database(settings.db_path)
    app.state.db.migrate()
    app.state.limiter = LoginLimiter()
    # 测试时可注入 httpx transport；生产为 None
    app.state.llm_transport = None

    # 老部署兼容：数据库里还没有配置行时，把 .env 里的 LLM_* 导入一次，之后以数据库为准
    with app.state.db.conn() as conn:
        if llm_config.bootstrap_from_env(conn, settings):
            logger.info("已把 .env 中的 LLM 配置导入数据库，后续请在设置页修改。")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict):
            return JSONResponse(detail, status_code=exc.status_code)
        return JSONResponse({"error": "error", "message": str(detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            {"error": "invalid_request", "message": "请求参数不合法", "issues": exc.errors()[:5]},
            status_code=400,
        )

    for module in (auth, words, cycle, stats, roots, annotate, llm):
        app.include_router(module.router)

    @app.get("/api/health")
    def health():
        config = llm_config.get_config(app.state.db.conn())
        return {
            "ok": True,
            "llmEnabled": config.enabled,
            "llmModel": config.model if config.enabled else "",
            "passwordConfigured": bool(settings.admin_password_hash),
        }

    dist = Path(settings.dist_dir)
    if not dist.is_absolute():
        dist = (ROOT / dist).resolve()
    index_file = dist / "index.html"
    if dist.is_dir() and index_file.is_file():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", ImmutableStaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"error": "not_found", "message": "接口不存在"}, status_code=404)
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist in candidate.parents:
                return _no_cache(FileResponse(candidate))
            return _no_cache(FileResponse(index_file))

    else:

        @app.get("/")
        def placeholder():
            return JSONResponse(
                {
                    "ok": True,
                    "message": "前端尚未构建（或 dist 不存在），请运行 npm run build，开发时请用 npm run dev。",
                }
            )

    return app


app = create_app()
