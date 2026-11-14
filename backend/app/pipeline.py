"""词源标注流水线：任务入队、上下文组装、批量调用模型、增量合并。"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from . import etymology, llm, llm_config
from .db import Database
from .util import now_iso


def enqueue(conn: sqlite3.Connection, word_ids: list[int]) -> int:
    """为还没标注的词排队（已有 pending/running 任务的不重复入队）。"""
    queued = 0
    stamp = now_iso()
    for word_id in word_ids:
        exists = conn.execute(
            """SELECT 1 FROM jobs WHERE kind = 'annotation' AND status IN ('pending', 'running')
               AND payload_json LIKE ?""",
            (f'%"wordId": {word_id}%',),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            "INSERT INTO jobs(kind, payload_json, status, created_at, updated_at) VALUES('annotation', ?, 'pending', ?, ?)",
            (json.dumps({"wordId": word_id}), stamp, stamp),
        )
        etymology.mark_annotation_pending(conn, word_id)
        queued += 1
    return queued


def _load_words(conn: sqlite3.Connection, word_ids: list[int]) -> list[dict[str, Any]]:
    rows = []
    for word_id in word_ids:
        row = conn.execute("SELECT id, term, meaning FROM words WHERE id = ?", (word_id,)).fetchone()
        if row is not None:
            rows.append({"id": int(row["id"]), "term": row["term"], "meaning": row["meaning"]})
    return rows


def _finish_job(conn: sqlite3.Connection, job_id: int, status: str, error: str = "") -> None:
    conn.execute(
        "UPDATE jobs SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ? WHERE id = ?",
        (status, error, now_iso(), job_id),
    )


def annotate_words(
    db: Database,
    word_ids: list[int],
    *,
    transport: Any | None = None,
) -> dict[str, Any]:
    """同步拆解一批单词并写入词根库；失败时把任务置为 skipped/failed 并记录原因。

    大模型配置从数据库读取（设置页维护），不再依赖 .env。
    """
    unique_ids = list(dict.fromkeys(int(w) for w in word_ids))
    if not unique_ids:
        return {"ok": 0, "failed": 0, "skipped": 0, "error": ""}
    conn = db.conn()
    config = llm_config.get_config(conn)
    with conn:
        enqueue(conn, unique_ids)
        words = _load_words(conn, unique_ids)
        if not words:
            return {"ok": 0, "failed": 0, "skipped": 0, "error": "单词不存在"}
        roots = etymology.roots_context(conn)
        affixes = etymology.affixes_context(conn)
        connected_at_start = len(roots)

    if not config.enabled:
        message = "未配置大模型接口（在设置页填写 Base URL 与模型名）"
        with conn:
            for word in words:
                etymology.mark_annotation_pending(conn, word["id"], message)
                conn.execute(
                    """UPDATE jobs SET status = 'skipped', last_error = ?, updated_at = ?
                       WHERE kind='annotation' AND status IN ('pending','running') AND payload_json LIKE ?""",
                    (message, now_iso(), f'%"wordId": {word["id"]}%'),
                )
        return {
            "ok": 0,
            "failed": 0,
            "skipped": len(words),
            "error": message + "，已跳过自动标注（可用离线标注导入）",
            "rootsInContext": connected_at_start,
        }

    result: dict[str, Any] = {"ok": 0, "failed": 0, "skipped": 0, "error": "", "items": []}
    batch_size = max(1, min(int(config.batch_size), 20))
    for start in range(0, len(words), batch_size):
        batch = words[start : start + batch_size]
        try:
            items = llm.annotate_batch(
                config,
                [{"term": w["term"], "meaning": w["meaning"]} for w in batch],
                roots,
                affixes,
                transport=transport,
            )
        except (llm.LLMError, llm.LLMNotConfigured) as exc:
            with conn:
                for word in batch:
                    conn.execute(
                        "UPDATE annotations SET status = 'failed', error = ?, updated_at = ? WHERE word_id = ?",
                        (str(exc)[:300], now_iso(), word["id"]),
                    )
            result["failed"] += len(batch)
            result["error"] = str(exc)
            continue
        by_term = {w["term"].lower(): w["id"] for w in batch}
        with conn:
            for item in items:
                word_id = by_term.get(str(item.get("word", "")).lower())
                if word_id is None:
                    continue
                etymology.save_annotation(
                    conn,
                    word_id,
                    item,
                    source="llm",
                    model=config.model,
                    prompt_version=llm.PROMPT_VERSION,
                )
                result["ok"] += 1
                result["items"].append({"wordId": word_id, "term": item.get("word")})
            # 下一批带上刚学到的新词根，形成增量累积
            roots = etymology.roots_context(conn)
            affixes = etymology.affixes_context(conn)
    with conn:
        for word in words:
            status = etymology.annotation_status(conn, word["id"])
            conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE kind='annotation' AND payload_json LIKE ? AND status IN ('pending','running')",
                ("done" if status == "ok" else "failed", now_iso(), f'%"wordId": {word["id"]}%'),
            )
    result["rootsInLibrary"] = len(roots)
    return result


def import_annotations(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
    *,
    source: str = "seed",
    model: str = "",
) -> dict[str, Any]:
    """离线导入标注（与流水线同一套幂等合并逻辑）。"""
    stats = {"ok": 0, "skipped": 0, "roots": 0, "affixes": 0, "links": 0, "errors": []}
    for item in items:
        term = str(item.get("word") or item.get("term") or "").strip()
        if not term:
            stats["skipped"] += 1
            continue
        word_id = etymology.find_word_id(conn, term)
        if word_id is None:
            stats["skipped"] += 1
            stats["errors"].append(f"词库中不存在：{term}")
            continue
        merged = etymology.save_annotation(
            conn,
            word_id,
            item,
            source=str(item.get("source") or source),
            model=model,
            prompt_version=str(item.get("promptVersion") or ""),
        )
        stats["ok"] += 1
        stats["roots"] += merged["roots"]
        stats["affixes"] += merged["affixes"]
        stats["links"] += merged["links"]
    stats["errors"] = stats["errors"][:20]
    return stats


def pending_job_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM jobs WHERE kind='annotation' AND status IN ('pending','running')"
    ).fetchone()
    return int(row["n"])


def process_pending(
    db: Database, limit: int = 40, *, transport: Any | None = None
) -> dict[str, Any]:
    """处理排队中的标注任务（由导入后触发或手动调用）。"""
    conn = db.conn()
    rows = conn.execute(
        "SELECT id, payload_json FROM jobs WHERE kind='annotation' AND status='pending' ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        return {"processed": 0}
    word_ids = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
        word_id = payload.get("wordId")
        if isinstance(word_id, int):
            word_ids.append(word_id)
    result = annotate_words(db, word_ids, transport=transport)
    result["processed"] = len(word_ids)
    return result
