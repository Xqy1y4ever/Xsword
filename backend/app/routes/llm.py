"""大模型接口配置：读取、保存、连通性测试。

配置存在数据库 llm_config 表里，运行时不读 .env。
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import llm, llm_config
from ..deps import auth, get_conn
from ..schemas import LlmConfigIn

router = APIRouter(prefix="/api/llm-config", tags=["llm"])


def _validate_base_url(value: str) -> None:
    if value and not value.lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_base_url", "message": "Base URL 需要以 http:// 或 https:// 开头"},
        )


@router.get("")
def read_config(conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    return llm_config.public_config(llm_config.get_config(conn))


@router.put("")
def write_config(
    payload: LlmConfigIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    if payload.baseUrl is not None:
        _validate_base_url(payload.baseUrl.strip())
    with conn:
        config = llm_config.save_config(
            conn,
            base_url=payload.baseUrl,
            api_key=payload.apiKey,
            model=payload.model,
            batch_size=payload.batchSize,
        )
    return llm_config.public_config(config)


@router.post("/test")
def test_config(
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    config = llm_config.get_config(conn)
    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail={"error": "llm_not_configured", "message": "请先填写 Base URL 与模型名并保存"},
        )
    try:
        return llm.test_connection(config, transport=getattr(request.app.state, "llm_transport", None))
    except llm.LLMNotConfigured as exc:
        raise HTTPException(status_code=400, detail={"error": "llm_not_configured", "message": str(exc)}) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail={"error": "llm_unreachable", "message": str(exc)}) from exc
