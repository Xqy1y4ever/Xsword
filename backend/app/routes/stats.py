"""统计：今日、累计、错词榜、近 7 天。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from .. import cycle
from ..config import Settings
from ..deps import auth, get_conn, get_settings

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats(
    conn: sqlite3.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
    _: dict = Depends(auth),
):
    snapshot = cycle.today_snapshot(conn, settings.timezone)
    weak_rows = conn.execute(
        """SELECT w.id, w.term, w.meaning, p.mastery, p.wrong, p.correct, p.user_mark, p.seen
           FROM progress p JOIN words w ON w.id = p.word_id
           WHERE p.seen > 0
           ORDER BY p.wrong DESC, p.mastery ASC LIMIT 10"""
    ).fetchall()
    weak = [
        {
            "wordId": int(r["id"]),
            "term": r["term"],
            "meaning": r["meaning"],
            "mastery": round(float(r["mastery"]), 1),
            "wrong": int(r["wrong"]),
            "correct": int(r["correct"]),
            "userMark": int(r["user_mark"]),
            "seen": int(r["seen"]),
        }
        for r in weak_rows
    ]
    history_rows = conn.execute(
        """SELECT date, COUNT(*) AS answered, COALESCE(SUM(correct), 0) AS correct,
                  COALESCE(AVG(response_ms), 0) AS avg_ms
           FROM daily_log GROUP BY date ORDER BY date DESC LIMIT 7"""
    ).fetchall()
    history = [
        {
            "date": r["date"],
            "answered": int(r["answered"]),
            "correct": int(r["correct"]),
            "accuracy": round(100 * int(r["correct"]) / int(r["answered"]), 1) if r["answered"] else 0,
            "avgResponseMs": round(float(r["avg_ms"])),
        }
        for r in reversed(history_rows)
    ]
    totals = conn.execute(
        """SELECT COALESCE(SUM(seen), 0) AS seen, COALESCE(SUM(correct), 0) AS correct,
                  COALESCE(SUM(wrong), 0) AS wrong
           FROM progress"""
    ).fetchone()
    total_seen = int(totals["seen"])
    total_correct = int(totals["correct"])
    cycle_total = int(
        conn.execute("SELECT COUNT(*) AS n FROM cycles WHERE finished_at IS NOT NULL").fetchone()["n"]
    )
    cycle_today = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM cycles WHERE date = ? AND finished_at IS NOT NULL",
            (snapshot["date"],),
        ).fetchone()["n"]
    )
    return {
        **snapshot,
        "weakWords": weak,
        "history": history,
        "totals": {
            "seen": total_seen,
            "correct": total_correct,
            "wrong": int(totals["wrong"]),
            "accuracy": round(100 * total_correct / total_seen, 1) if total_seen else 0,
            "cycles": cycle_total,
            "cyclesToday": cycle_today,
        },
        "pendingAnnotations": snapshot["annotations"]["pending"],
    }
