"""词源标注：手动触发流水线、离线导入、状态查询。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request

from .. import pipeline
from ..deps import auth, get_conn
from ..schemas import AnnotateImportIn, AnnotateIn

router = APIRouter(prefix="/api/annotate", tags=["annotate"])


@router.post("")
def annotate(
    payload: AnnotateIn,
    request: Request,
    _: dict = Depends(auth),
):
    return pipeline.annotate_words(
        request.app.state.db,
        payload.wordIds,
        transport=getattr(request.app.state, "llm_transport", None),
    )


@router.post("/import")
def import_annotations(
    payload: AnnotateImportIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    items = [item.model_dump() for item in payload.items]
    with conn:
        return pipeline.import_annotations(conn, items, source="seed")


@router.get("/status")
def status(conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM annotations GROUP BY status").fetchall()
    counts = {r["status"]: int(r["n"]) for r in rows}
    total = int(conn.execute("SELECT COUNT(*) AS n FROM words").fetchone()["n"])
    return {
        "total": total,
        "byStatus": counts,
        "annotated": counts.get("ok", 0),
        "pendingJobs": pipeline.pending_job_count(conn),
        "missing": max(0, total - sum(counts.values())),
    }
