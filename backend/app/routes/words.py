"""词库：CRUD、导入导出、自评标记、标注读取。"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response

from .. import etymology, llm_config, pipeline, scoring, util
from ..deps import auth, get_conn
from ..schemas import AnnotationIn, ImportIn, MarkIn, PurgeIn, WordIn, WordPatch

router = APIRouter(prefix="/api/words", tags=["words"])

WORD_FIELDS = ("term", "meaning", "alt", "phonetic", "pos", "example", "tags")


def _serialize(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    progress = conn.execute("SELECT * FROM progress WHERE word_id = ?", (row["id"],)).fetchone()
    annotation = conn.execute(
        "SELECT status, source, updated_at FROM annotations WHERE word_id = ?", (row["id"],)
    ).fetchone()
    mastery = float(progress["mastery"]) if progress else 0.0
    label, code = scoring.mastery_level(mastery)
    return {
        "id": int(row["id"]),
        "term": row["term"],
        "meaning": row["meaning"],
        "alt": row["alt"],
        "phonetic": row["phonetic"],
        "pos": row["pos"],
        "example": row["example"],
        "tags": row["tags"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "mastery": mastery,
        "masteryLabel": label,
        "masteryCode": code,
        "userMark": int(progress["user_mark"]) if progress else 0,
        "seen": int(progress["seen"]) if progress else 0,
        "correct": int(progress["correct"]) if progress else 0,
        "wrong": int(progress["wrong"]) if progress else 0,
        "lastSeenAt": progress["last_seen_at"] if progress else None,
        "annotationStatus": annotation["status"] if annotation else "missing",
        "annotationSource": annotation["source"] if annotation else "",
    }


def _fetch_word(conn: sqlite3.Connection, word_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "单词不存在"})
    return row


def _ensure_progress(conn: sqlite3.Connection, word_id: int) -> sqlite3.Row:
    conn.execute("INSERT OR IGNORE INTO progress(word_id, updated_at) VALUES(?, ?)", (word_id, util.now_iso()))
    return conn.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,)).fetchone()


def parse_import_text(text: str) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """每行一条：单词 <TAB|逗号|等号|冒号> 释义 [<TAB> 标签]。"""
    rows: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split("\t")]
        if len(fields) >= 2 and fields[0] and fields[1]:
            term, meaning, tags = fields[0], fields[1], (fields[2] if len(fields) > 2 else "")
        else:
            term = meaning = tags = ""
            for separator in ("=", "：", ":", ",", "，", "|"):
                if separator in line:
                    head, tail = line.split(separator, 1)
                    term, meaning = head.strip(), tail.strip()
                    break
            if not term or not meaning:
                errors.append({"line": index, "reason": "无法解析（需要 单词 + 分隔符 + 释义）", "text": line[:80]})
                continue
        if len(term) > 120 or len(meaning) > 300:
            errors.append({"line": index, "reason": "过长", "text": line[:80]})
            continue
        rows.append({"term": term, "meaning": meaning, "tags": tags})
    return rows, errors


@router.get("")
def list_words(
    q: str = Query(default="", max_length=120),
    tag: str = Query(default="", max_length=60),
    sort: str = Query(default="newest", pattern="^(newest|term|weakest|mastered)$"),
    annotation: str = Query(default="", pattern="^(|missing|ok|pending|failed)$"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    clauses: list[str] = []
    params: list[Any] = []
    if q:
        clauses.append("(w.term LIKE ? OR w.meaning LIKE ? OR w.tags LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if tag:
        clauses.append("w.tags LIKE ?")
        params.append(f"%{tag}%")
    if annotation == "missing":
        clauses.append("a.status IS NULL")
    elif annotation == "pending":
        clauses.append("a.status IN ('pending', 'failed')")
    elif annotation in ("ok", "failed"):
        clauses.append("a.status = ?")
        params.append(annotation)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order = {
        "newest": "w.id DESC",
        "term": "w.term COLLATE NOCASE ASC",
        "weakest": "COALESCE(p.mastery, 0) ASC, w.id ASC",
        "mastered": "COALESCE(p.mastery, 0) DESC, w.id ASC",
    }[sort]
    total = int(
        conn.execute(
            f"SELECT COUNT(*) AS n FROM words w LEFT JOIN annotations a ON a.word_id = w.id {where}", params
        ).fetchone()["n"]
    )
    rows = conn.execute(
        f"""SELECT w.* FROM words w
            LEFT JOIN progress p ON p.word_id = w.id
            LEFT JOIN annotations a ON a.word_id = w.id
            {where} ORDER BY {order} LIMIT ? OFFSET ?""",
        (*params, pageSize, (page - 1) * pageSize),
    ).fetchall()
    return {
        "items": [_serialize(conn, row) for row in rows],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/export")
def export_words(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    rows = conn.execute("SELECT * FROM words ORDER BY id").fetchall()
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["term", "meaning", "alt", "phonetic", "pos", "example", "tags"])
        for row in rows:
            writer.writerow([row[f] for f in WORD_FIELDS])
        return Response(
            content=buffer.getvalue().encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="words.csv"'},
        )
    payload = {"version": 1, "words": [{f: row[f] for f in WORD_FIELDS} for row in rows]}
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="words.json"'},
    )


@router.post("", status_code=201)
def create_word(
    payload: WordIn,
    request: Request,
    background: BackgroundTasks,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    stamp = util.now_iso()
    try:
        with conn:
            cur = conn.execute(
                """INSERT INTO words(term, meaning, alt, phonetic, pos, example, tags, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    payload.term.strip(),
                    payload.meaning.strip(),
                    payload.alt.strip(),
                    payload.phonetic.strip(),
                    payload.pos.strip(),
                    payload.example.strip(),
                    payload.tags.strip(),
                    stamp,
                    stamp,
                ),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail={"error": "duplicate_term", "message": "该单词已存在"})
    word_id = int(cur.lastrowid)
    if llm_config.is_enabled(conn):
        with conn:
            pipeline.enqueue(conn, [word_id])
        background.add_task(
            pipeline.process_pending,
            request.app.state.db,
            20,
            transport=getattr(request.app.state, "llm_transport", None),
        )
    row = _fetch_word(conn, word_id)
    return _serialize(conn, row)


@router.post("/import")
def import_words(
    payload: ImportIn,
    request: Request,
    background: BackgroundTasks,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    rows, errors = parse_import_text(payload.text)
    added: list[int] = []
    skipped = list(errors)
    stamp = util.now_iso()
    with conn:
        for item in rows:
            exists = conn.execute(
                "SELECT id FROM words WHERE lower(term) = lower(?)", (item["term"],)
            ).fetchone()
            if exists:
                skipped.append({"line": 0, "reason": "已存在", "term": item["term"]})
                continue
            cur = conn.execute(
                """INSERT INTO words(term, meaning, alt, phonetic, pos, example, tags, created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (item["term"], item["meaning"], "", "", "", "", item["tags"], stamp, stamp),
            )
            added.append(int(cur.lastrowid))
    enqueued = 0
    if added and llm_config.is_enabled(conn):
        with conn:
            enqueued = pipeline.enqueue(conn, added)
        background.add_task(
            pipeline.process_pending,
            request.app.state.db,
            40,
            transport=getattr(request.app.state, "llm_transport", None),
        )
    return {"added": len(added), "skipped": skipped[:50], "enqueued": enqueued}


@router.post("/purge")
def purge_words(
    payload: PurgeIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    if payload.confirm != "DELETE":
        raise HTTPException(status_code=400, detail={"error": "confirm_required", "message": "请输入 DELETE 确认清空"})
    with conn:
        conn.execute("DELETE FROM cycle_items")
        conn.execute("DELETE FROM cycles")
        conn.execute("DELETE FROM words")
        conn.execute("DELETE FROM daily_log")
        conn.execute("DELETE FROM jobs")
        conn.execute("DELETE FROM roots")
        conn.execute("DELETE FROM affixes")
    return {"ok": True}


@router.get("/{word_id}")
def get_word(word_id: int, conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    return _serialize(conn, _fetch_word(conn, word_id))


@router.patch("/{word_id}")
def patch_word(
    word_id: int,
    payload: WordPatch,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    _fetch_word(conn, word_id)
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return _serialize(conn, _fetch_word(conn, word_id))
    if "term" in updates:
        duplicate = conn.execute(
            "SELECT id FROM words WHERE lower(term) = lower(?) AND id != ?", (updates["term"].strip(), word_id)
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail={"error": "duplicate_term", "message": "该单词已存在"})
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = [str(v).strip() for v in updates.values()]
    with conn:
        conn.execute(
            f"UPDATE words SET {assignments}, updated_at = ? WHERE id = ?",
            (*values, util.now_iso(), word_id),
        )
    return _serialize(conn, _fetch_word(conn, word_id))


@router.delete("/{word_id}", status_code=200)
def delete_word(word_id: int, conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    _fetch_word(conn, word_id)
    with conn:
        conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
    return {"ok": True}


@router.put("/{word_id}/mark")
def set_mark(
    word_id: int,
    payload: MarkIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    _fetch_word(conn, word_id)
    with conn:
        progress = _ensure_progress(conn, word_id)
        anchor = scoring.mark_anchor(payload.mark)
        mastery = (
            float(anchor)
            if anchor is not None
            else scoring.mastery_score(
                int(progress["seen"]),
                int(progress["correct"]),
                float(progress["speed_score_sum"]),
                payload.mark,
            )
        )
        conn.execute(
            "UPDATE progress SET user_mark = ?, mastery = ?, updated_at = ? WHERE word_id = ?",
            (payload.mark, mastery, util.now_iso(), word_id),
        )
    return {"wordId": word_id, "userMark": payload.mark, "mastery": mastery}


@router.get("/{word_id}/annotation")
def get_annotation(word_id: int, conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    _fetch_word(conn, word_id)
    return etymology.memory_card(conn, word_id)


@router.patch("/{word_id}/annotation")
def patch_annotation(
    word_id: int,
    payload: AnnotationIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    _fetch_word(conn, word_id)
    with conn:
        etymology.save_annotation(
            conn,
            word_id,
            payload.model_dump(),
            source="manual",
            model="",
            prompt_version="manual",
        )
    return etymology.memory_card(conn, word_id)
