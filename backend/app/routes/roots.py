"""词根库 / 词缀库 / 词族。"""
from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth, get_conn

router = APIRouter(prefix="/api", tags=["roots"])


def _words_for_root(conn: sqlite3.Connection, root_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT w.id, w.term, w.meaning, w.phonetic, wr.form, COALESCE(p.mastery, 0) AS mastery,
                  COALESCE(p.user_mark, 0) AS user_mark
           FROM word_roots wr JOIN words w ON w.id = wr.word_id
           LEFT JOIN progress p ON p.word_id = w.id
           WHERE wr.root_id = ? ORDER BY mastery ASC, w.term COLLATE NOCASE""",
        (root_id,),
    ).fetchall()
    return [
        {
            "wordId": int(r["id"]),
            "term": r["term"],
            "meaning": r["meaning"],
            "phonetic": r["phonetic"],
            "form": r["form"],
            "mastery": round(float(r["mastery"]), 1),
            "userMark": int(r["user_mark"]),
        }
        for r in rows
    ]


def _words_for_affix(conn: sqlite3.Connection, affix_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT w.id, w.term, w.meaning, wa.form, COALESCE(p.mastery, 0) AS mastery,
                  COALESCE(p.user_mark, 0) AS user_mark
           FROM word_affixes wa JOIN words w ON w.id = wa.word_id
           LEFT JOIN progress p ON p.word_id = w.id
           WHERE wa.affix_id = ? ORDER BY mastery ASC, w.term COLLATE NOCASE""",
        (affix_id,),
    ).fetchall()
    return [
        {
            "wordId": int(r["id"]),
            "term": r["term"],
            "meaning": r["meaning"],
            "form": r["form"],
            "mastery": round(float(r["mastery"]), 1),
            "userMark": int(r["user_mark"]),
        }
        for r in rows
    ]


@router.get("/roots")
def list_roots(
    q: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=30, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    params: list[Any] = []
    where = ""
    if q:
        where = "WHERE r.key LIKE ? OR r.gloss LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    total = int(conn.execute(f"SELECT COUNT(*) AS n FROM roots r {where}", params).fetchone()["n"])
    rows = conn.execute(
        f"""SELECT r.*, (SELECT COUNT(DISTINCT word_id) FROM word_roots wr WHERE wr.root_id = r.id) AS words
            FROM roots r {where} ORDER BY words DESC, r.usage DESC, r.key LIMIT ? OFFSET ?""",
        (*params, pageSize, (page - 1) * pageSize),
    ).fetchall()
    return {
        "items": [
            {
                "id": int(r["id"]),
                "key": r["key"],
                "gloss": r["gloss"],
                "origin": r["origin"],
                "note": r["note"],
                "usage": int(r["usage"]),
                "words": int(r["words"] or 0),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/roots/{root_id}")
def get_root(root_id: int, conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    row = conn.execute("SELECT * FROM roots WHERE id = ?", (root_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "词根不存在"})
    related = conn.execute(
        """SELECT r2.id, r2.key, r2.gloss, COUNT(*) AS shared
           FROM word_roots a
           JOIN word_roots b ON b.word_id = a.word_id AND b.root_id != a.root_id
           JOIN roots r2 ON r2.id = b.root_id
           WHERE a.root_id = ? GROUP BY r2.id ORDER BY shared DESC, r2.key LIMIT 10""",
        (root_id,),
    ).fetchall()
    return {
        "id": int(row["id"]),
        "key": row["key"],
        "gloss": row["gloss"],
        "origin": row["origin"],
        "note": row["note"],
        "usage": int(row["usage"]),
        "words": _words_for_root(conn, root_id),
        "relatedRoots": [
            {"id": int(r["id"]), "key": r["key"], "gloss": r["gloss"], "shared": int(r["shared"])}
            for r in related
        ],
    }


@router.get("/affixes")
def list_affixes(
    type: str = Query(default="", pattern="^(|prefix|suffix)$"),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    params: list[Any] = []
    where = ""
    if type:
        where = "WHERE a.type = ?"
        params = [type]
    rows = conn.execute(
        f"""SELECT a.*, (SELECT COUNT(DISTINCT word_id) FROM word_affixes wa WHERE wa.affix_id = a.id) AS words
            FROM affixes a {where} ORDER BY words DESC, a.usage DESC, a.key LIMIT 300""",
        params,
    ).fetchall()
    return {
        "items": [
            {
                "id": int(r["id"]),
                "key": r["key"],
                "type": r["type"],
                "gloss": r["gloss"],
                "note": r["note"],
                "usage": int(r["usage"]),
                "words": int(r["words"] or 0),
            }
            for r in rows
        ]
    }


@router.get("/affixes/{affix_id}")
def get_affix(affix_id: int, conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    row = conn.execute("SELECT * FROM affixes WHERE id = ?", (affix_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "词缀不存在"})
    return {
        "id": int(row["id"]),
        "key": row["key"],
        "type": row["type"],
        "gloss": row["gloss"],
        "note": row["note"],
        "usage": int(row["usage"]),
        "words": _words_for_affix(conn, affix_id),
    }
