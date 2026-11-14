"""大模型接口配置：存数据库单行，运行时以库为准。

.env 里的 LLM_* 只用于首次启动时引导导入（bootstrap_from_env），之后一律以数据库为准，
由设置页或 /api/llm-config 修改。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .util import now_iso

DEFAULT_BATCH_SIZE = 20
MAX_BATCH_SIZE = 50


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    batch_size: int = DEFAULT_BATCH_SIZE
    updated_at: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.base_url.strip() and self.model.strip())


def _clamp_batch(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BATCH_SIZE
    return max(1, min(MAX_BATCH_SIZE, number))


def get_config(conn: sqlite3.Connection) -> LLMConfig:
    row = conn.execute("SELECT * FROM llm_config WHERE id = 1").fetchone()
    if row is None:
        return LLMConfig()
    return LLMConfig(
        base_url=str(row["base_url"] or ""),
        api_key=str(row["api_key"] or ""),
        model=str(row["model"] or ""),
        batch_size=_clamp_batch(row["batch_size"]),
        updated_at=str(row["updated_at"] or ""),
    )


def save_config(
    conn: sqlite3.Connection,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    batch_size: int | None = None,
) -> LLMConfig:
    current = get_config(conn)
    next_base = current.base_url if base_url is None else base_url.strip()
    next_key = current.api_key if api_key is None else api_key.strip()
    next_model = current.model if model is None else model.strip()
    next_batch = current.batch_size if batch_size is None else _clamp_batch(batch_size)
    conn.execute(
        """INSERT INTO llm_config(id, base_url, api_key, model, batch_size, updated_at)
           VALUES(1, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             base_url = excluded.base_url,
             api_key = excluded.api_key,
             model = excluded.model,
             batch_size = excluded.batch_size,
             updated_at = excluded.updated_at""",
        (next_base, next_key, next_model, next_batch, now_iso()),
    )
    return get_config(conn)


def is_enabled(conn: sqlite3.Connection) -> bool:
    return get_config(conn).enabled


def public_config(config: LLMConfig) -> dict[str, Any]:
    """对外返回的配置：绝不返回明文 API Key。"""
    hint = ""
    if config.api_key:
        hint = f"…{config.api_key[-4:]}" if len(config.api_key) >= 4 else "…"
    return {
        "baseUrl": config.base_url,
        "model": config.model,
        "batchSize": config.batch_size,
        "apiKeySet": bool(config.api_key),
        "apiKeyHint": hint,
        "enabled": config.enabled,
        "updatedAt": config.updated_at,
    }


def bootstrap_from_env(conn: sqlite3.Connection, legacy: Any) -> bool:
    """数据库还没有配置行时，把 .env 里的 LLM_* 导入一次（老部署兼容）。"""
    exists = conn.execute("SELECT 1 FROM llm_config WHERE id = 1").fetchone()
    if exists:
        return False
    base = str(getattr(legacy, "llm_base_url", "") or "")
    key = str(getattr(legacy, "llm_api_key", "") or "")
    model = str(getattr(legacy, "llm_model", "") or "")
    batch = getattr(legacy, "llm_batch_size", DEFAULT_BATCH_SIZE)
    if not (base or key or model):
        return False
    save_config(conn, base_url=base, api_key=key, model=model, batch_size=batch)
    return True
