"""循环制练习：开始/继续循环、出题、答题结算、今日概览。

一个循环 = 用户设定词数的一批题目；循环内单词不重复；
每个单词的题型在循环开始时按当时的熟练度确定（<60 选义，60–90 拼写，>90 不进循环）。
每天可以完成多个循环。
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date as Date
from typing import Any

from . import etymology, quiz, scoring, util

DEFAULT_CYCLE_SIZE = 20
MIN_CYCLE_SIZE = 1
MAX_CYCLE_SIZE = 200
DEFAULT_CHOICE_RATIO = 0.6
MIN_RESPONSE_MS = 150
MAX_RESPONSE_MS = 120_000


class CycleError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM cycle_settings WHERE id = 1").fetchone()
    size = int(row["size"]) if row is not None else DEFAULT_CYCLE_SIZE
    ratio = float(row["choice_ratio"]) if row is not None else DEFAULT_CHOICE_RATIO
    return {
        "cycleSize": max(MIN_CYCLE_SIZE, min(MAX_CYCLE_SIZE, size)),
        "choiceRatio": round(max(0.0, min(1.0, ratio)), 2),
    }


def update_settings(
    conn: sqlite3.Connection, cycle_size: int, choice_ratio: float | None = None
) -> dict[str, Any]:
    try:
        size = int(cycle_size)
    except (TypeError, ValueError):
        raise CycleError("invalid_cycle_size", "每循环词数必须是整数")
    size = max(MIN_CYCLE_SIZE, min(MAX_CYCLE_SIZE, size))

    current = get_settings(conn)
    ratio = current["choiceRatio"] if choice_ratio is None else float(choice_ratio)
    if not (0.0 <= ratio <= 1.0):
        raise CycleError("invalid_choice_ratio", "选义比例必须在 0–100% 之间")
    ratio = round(ratio, 2)

    conn.execute(
        """INSERT INTO cycle_settings(id, size, choice_ratio, updated_at) VALUES(1, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             size = excluded.size,
             choice_ratio = excluded.choice_ratio,
             updated_at = excluded.updated_at""",
        (size, ratio, util.now_iso()),
    )
    return get_settings(conn)


def _cycle_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "date": row["date"],
        "size": int(row["size"]),
        "answered": int(row["answered"]),
        "correct": int(row["correct"]),
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
        "finished": row["finished_at"] is not None,
    }


def _cycle_row(conn: sqlite3.Connection, cycle_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
    if row is None:
        raise CycleError("cycle_not_found", "循环不存在", status=404)
    return row


def _exclude_clause(word_ids) -> tuple[str, list[int]]:
    ids = list(word_ids)
    if not ids:
        return "", []
    return " AND w.id NOT IN (" + ",".join("?" for _ in ids) + ")", ids


def active_cycle(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM cycles WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return _cycle_dict(row) if row is not None else None


def eligible_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        """SELECT COUNT(*) AS n FROM words w
           LEFT JOIN progress p ON p.word_id = w.id
           WHERE COALESCE(p.mastery, 0) <= ?""",
        (scoring.MASTERY_EXCLUDE,),
    ).fetchone()
    return int(row["n"])


def _banned_repeat_words(conn: sqlite3.Connection) -> set[int]:
    """最近两个循环里连续都出现过的词：本轮不能再选（避免连续出现第三次）。"""
    rows = conn.execute("SELECT id FROM cycles ORDER BY id DESC LIMIT 2").fetchall()
    if len(rows) < 2:
        return set()
    latest = int(rows[0]["id"])
    previous = int(rows[1]["id"])
    repeated = conn.execute(
        """SELECT word_id FROM cycle_items WHERE cycle_id = ?
           INTERSECT
           SELECT word_id FROM cycle_items WHERE cycle_id = ?""",
        (latest, previous),
    ).fetchall()
    return {int(row["word_id"]) for row in repeated}


def start_cycle(conn: sqlite3.Connection, tz_name: str) -> dict[str, Any]:
    """开始新循环；若已有未完成循环则直接返回它（继续）。"""
    existing = active_cycle(conn)
    if existing is not None:
        return {"cycle": existing, "resumed": True, "eligible": None}

    settings = get_settings(conn)
    size = settings["cycleSize"]
    choice_target = scoring.mode_split(size, settings["choiceRatio"])
    spell_target = size - choice_target
    banned = _banned_repeat_words(conn)

    # 释义题池：熟练度 ≤ 60；拼写题池：熟练度 > 50；两个池都按熟练度升序（低的优先）
    chosen: dict[int, float] = {}
    modes: dict[int, str] = {}

    choice_exclude_sql, choice_exclude_params = _exclude_clause(banned)
    choice_rows = conn.execute(
        f"""SELECT w.id AS id, COALESCE(p.mastery, 0) AS mastery
            FROM words w
            LEFT JOIN progress p ON p.word_id = w.id
            WHERE COALESCE(p.mastery, 0) <= ?{choice_exclude_sql}
            ORDER BY COALESCE(p.mastery, 0) ASC, RANDOM()
            LIMIT ?""",
        (scoring.CHOICE_MAX_MASTERY, *choice_exclude_params, choice_target),
    ).fetchall()
    for row in choice_rows:
        chosen[int(row["id"])] = float(row["mastery"])
        modes[int(row["id"])] = "en2cn"

    if spell_target > 0:
        exclude_sql, exclude_params = _exclude_clause(banned | set(chosen))
        spell_rows = conn.execute(
            f"""SELECT w.id AS id, COALESCE(p.mastery, 0) AS mastery
                FROM words w
                LEFT JOIN progress p ON p.word_id = w.id
                WHERE COALESCE(p.mastery, 0) > ? AND COALESCE(p.mastery, 0) <= ?{exclude_sql}
                ORDER BY COALESCE(p.mastery, 0) ASC, RANDOM()
                LIMIT ?""",
            (scoring.SPELLING_MIN_MASTERY, scoring.MASTERY_EXCLUDE, *exclude_params, spell_target),
        ).fetchall()
        for row in spell_rows:
            chosen[int(row["id"])] = float(row["mastery"])
            modes[int(row["id"])] = "cn2en"

    # 按门槛某类题不够时，用剩余可练词补齐（不会让 >60 的词出释义、也不会让 ≤50 的词出拼写）
    remaining = size - len(chosen)
    if remaining > 0:
        exclude_sql, exclude_params = _exclude_clause(banned | set(chosen))
        fill_rows = conn.execute(
            f"""SELECT w.id AS id, COALESCE(p.mastery, 0) AS mastery
                FROM words w
                LEFT JOIN progress p ON p.word_id = w.id
                WHERE COALESCE(p.mastery, 0) <= ?{exclude_sql}
                ORDER BY COALESCE(p.mastery, 0) ASC, RANDOM()
                LIMIT ?""",
            (scoring.MASTERY_EXCLUDE, *exclude_params, remaining),
        ).fetchall()
        choice_count = sum(1 for mode in modes.values() if mode == "en2cn")
        for row in fill_rows:
            word_id = int(row["id"])
            mastery = float(row["mastery"])
            if mastery > scoring.CHOICE_MAX_MASTERY:
                mode = "cn2en"
            elif mastery <= scoring.SPELLING_MIN_MASTERY:
                mode = "en2cn"
            else:
                mode = "en2cn" if choice_count < choice_target else "cn2en"
            chosen[word_id] = mastery
            modes[word_id] = mode
            if mode == "en2cn":
                choice_count += 1

    if not chosen:
        return {"cycle": None, "resumed": False, "eligible": 0}

    # 低熟练度优先：位置按熟练度升序；同分随机（不能按 id，否则会按词表导入顺序＝字母序成串出现）
    ordered = sorted(chosen.items(), key=lambda item: (item[1], random.random()))
    stamp = util.now_iso()
    day = util.today_str(tz_name)
    cursor = conn.execute(
        "INSERT INTO cycles(date, started_at, size, answered, correct) VALUES(?, ?, ?, 0, 0)",
        (day, stamp, len(ordered)),
    )
    cycle_id = int(cursor.lastrowid)
    for pos, (word_id, mastery) in enumerate(ordered):
        conn.execute(
            """INSERT INTO cycle_items(cycle_id, word_id, pos, mode, mastery_at_start)
               VALUES(?, ?, ?, ?, ?)""",
            (cycle_id, word_id, pos, modes[word_id], mastery),
        )
    return {"cycle": _cycle_dict(_cycle_row(conn, cycle_id)), "resumed": False, "eligible": len(ordered)}


def next_question(conn: sqlite3.Connection, cycle_id: int) -> dict[str, Any]:
    cycle = _cycle_row(conn, cycle_id)
    item = conn.execute(
        """SELECT ci.word_id, ci.mode, ci.pos AS item_pos, w.id, w.term, w.meaning,
                  w.phonetic, w.pos, w.alt
           FROM cycle_items ci JOIN words w ON w.id = ci.word_id
           WHERE ci.cycle_id = ? AND ci.answered = 0
           ORDER BY ci.pos LIMIT 1""",
        (cycle_id,),
    ).fetchone()
    if item is None:
        return {"finished": True, "cycle": _cycle_dict(cycle)}
    question = quiz.build_question(conn, item, item["mode"])
    question["cycleId"] = int(cycle_id)
    question["pos"] = int(item["item_pos"])
    question["progress"] = {
        "answered": int(cycle["answered"]),
        "total": int(cycle["size"]),
    }
    return {"finished": False, "question": question, "cycle": _cycle_dict(cycle)}


def _clamp_response(response_ms: int) -> int:
    if response_ms <= 0:
        return 60_000
    return max(MIN_RESPONSE_MS, min(MAX_RESPONSE_MS, response_ms))


def answer(conn: sqlite3.Connection, cycle_id: int, payload: dict[str, Any], tz_name: str) -> dict[str, Any]:
    cycle = _cycle_row(conn, cycle_id)
    if cycle["finished_at"] is not None:
        raise CycleError("cycle_finished", "这个循环已经完成了", status=409)
    word_id = int(payload.get("wordId") or 0)
    item = conn.execute(
        "SELECT * FROM cycle_items WHERE cycle_id = ? AND word_id = ?", (cycle_id, word_id)
    ).fetchone()
    if item is None:
        raise CycleError("word_not_in_cycle", "该单词不在当前循环里")
    if int(item["answered"]):
        raise CycleError("already_answered", "这道题已经答过了", status=409)
    word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
    if word is None:
        raise CycleError("word_not_found", "单词不存在", status=404)

    mode = str(item["mode"])
    action = str(payload.get("action") or "submit")
    if action not in ("submit", "dont_know", "mastered"):
        raise CycleError("invalid_action", "无法识别的操作")
    response_ms = _clamp_response(int(payload.get("responseMs") or 0))
    raw_answer = str(payload.get("answer") or "").strip()

    if action == "mastered":
        correct = True
        correct_answer = str(word["term"]) if mode == "cn2en" else str(word["meaning"])
    elif action == "dont_know":
        correct = False
        correct_answer = str(word["term"]) if mode == "cn2en" else str(word["meaning"])
    elif mode == "en2cn":
        correct = quiz.normalize_answer(raw_answer) == quiz.normalize_answer(str(word["meaning"]))
        correct_answer = str(word["meaning"])
    else:
        correct = quiz.is_correct(word, raw_answer)
        correct_answer = str(word["term"])

    day = util.today_str(tz_name)
    stamp = util.now_iso()
    progress = conn.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,)).fetchone()
    if progress is None:
        conn.execute(
            "INSERT OR IGNORE INTO progress(word_id, updated_at) VALUES(?, ?)", (word_id, stamp)
        )
        progress = conn.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,)).fetchone()

    mastery_before = float(progress["mastery"])
    forced_mark = 1 if action == "dont_know" else None
    snapshot = scoring.next_mastery(
        mastery_before,
        int(progress["seen"]),
        int(progress["correct"]),
        float(progress["speed_score_sum"]),
        int(progress["user_mark"]),
        is_correct=correct,
        response_ms=response_ms,
        mode=mode,
        action=action,
        forced_mark=forced_mark,
    )
    fast_ms = scoring.FAST_MS.get(mode, 5000)
    fast = int(progress["fast_count"]) + (1 if correct and response_ms <= fast_ms else 0)
    slow = int(progress["slow_count"]) + (1 if response_ms > fast_ms * 2 else 0)
    streak = int(progress["streak"]) + 1 if correct else 0
    conn.execute(
        """UPDATE progress SET seen = ?, correct = ?, wrong = ?, streak = ?, fast_count = ?, slow_count = ?,
             speed_score_sum = ?, user_mark = ?, mastery = ?, first_seen_date = COALESCE(first_seen_date, ?),
             last_seen_at = ?, last_result = ?, updated_at = ?
           WHERE word_id = ?""",
        (
            snapshot.seen,
            snapshot.correct,
            snapshot.wrong,
            streak,
            fast,
            slow,
            snapshot.speed_score_sum,
            snapshot.user_mark,
            snapshot.mastery,
            day,
            stamp,
            "correct" if correct else "wrong",
            stamp,
            word_id,
        ),
    )
    conn.execute(
        """INSERT INTO daily_log(date, word_id, mode, phase, correct, response_ms, created_at)
           VALUES(?, ?, ?, 'cycle', ?, ?, ?)""",
        (day, word_id, mode, 1 if correct else 0, response_ms, stamp),
    )
    conn.execute(
        """UPDATE cycle_items SET answered = 1, correct = ?, response_ms = ?, action = ?,
             mastery_before = ?, answered_at = ?
           WHERE cycle_id = ? AND word_id = ?""",
        (1 if correct else 0, response_ms, action, mastery_before, stamp, cycle_id, word_id),
    )
    conn.execute(
        "UPDATE cycles SET answered = answered + 1, correct = correct + ? WHERE id = ?",
        (1 if correct else 0, cycle_id),
    )
    fresh_cycle = _cycle_row(conn, cycle_id)
    finished = int(fresh_cycle["answered"]) >= int(fresh_cycle["size"])
    if finished:
        conn.execute("UPDATE cycles SET finished_at = ? WHERE id = ?", (stamp, cycle_id))
        fresh_cycle = _cycle_row(conn, cycle_id)

    label, code = scoring.mastery_level(snapshot.mastery)
    show_memory = action != "mastered" and (
        (not correct) or snapshot.mastery < scoring.MARK_ANCHORS[3]
    )
    memory = etymology.memory_card(conn, word_id) if show_memory else None
    return {
        "wordId": word_id,
        "term": word["term"],
        "meaning": word["meaning"],
        "phonetic": word["phonetic"],
        "pos": word["pos"],
        "mode": mode,
        "action": action,
        "correct": correct,
        "correctAnswer": correct_answer,
        "userAnswer": raw_answer,
        "responseMs": response_ms,
        "userMark": snapshot.user_mark,
        "masteryBefore": mastery_before,
        "masteryAfter": snapshot.mastery,
        "masteryLabel": label,
        "masteryCode": code,
        "levelUp": snapshot.mastery > mastery_before + 5,
        "showMemory": show_memory,
        "memory": memory,
        "cycle": {**_cycle_dict(fresh_cycle), "progress": {"answered": int(fresh_cycle["answered"]), "total": int(fresh_cycle["size"])}},
        "cycleFinished": bool(fresh_cycle["finished_at"]),
    }


def adjust_answer(conn: sqlite3.Connection, cycle_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """拼写题写完后追加选择：模糊 → 熟练度回滚到答题前；已熟练 → 提到 95（>90）。"""
    _cycle_row(conn, cycle_id)
    word_id = int(payload.get("wordId") or 0)
    choice = str(payload.get("choice") or "")
    if choice not in ("fuzzy", "mastered"):
        raise CycleError("invalid_choice", "无法识别的选项", status=400)
    item = conn.execute(
        "SELECT * FROM cycle_items WHERE cycle_id = ? AND word_id = ?", (cycle_id, word_id)
    ).fetchone()
    if item is None:
        raise CycleError("word_not_in_cycle", "该单词不在当前循环里", status=400)
    if not int(item["answered"]):
        raise CycleError("not_answered", "这道题还没作答", status=409)
    if str(item["mode"]) != "cn2en":
        raise CycleError("only_spelling", "只有拼写题可以选择「模糊 / 已熟练」", status=400)

    progress = conn.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,)).fetchone()
    if progress is None:
        raise CycleError("word_not_found", "单词不存在", status=404)
    before = float(progress["mastery"])

    if choice == "mastered":
        mastery = max(before, scoring.MASTERED_SPELLING_SCORE)
        mark = 4
    else:
        if item["mastery_before"] is None:
            raise CycleError("rollback_unavailable", "没有记录答题前的熟练度，无法回滚", status=409)
        mastery = float(item["mastery_before"])
        mark = scoring.stage_of(mastery)

    stamp = util.now_iso()
    conn.execute(
        "UPDATE progress SET mastery = ?, user_mark = ?, updated_at = ? WHERE word_id = ?",
        (mastery, mark, stamp, word_id),
    )
    conn.execute(
        "UPDATE cycle_items SET adjust_choice = ? WHERE cycle_id = ? AND word_id = ?",
        (choice, cycle_id, word_id),
    )
    label, code = scoring.mastery_level(mastery)
    return {
        "wordId": word_id,
        "choice": choice,
        "masteryBefore": before,
        "masteryAfter": round(mastery, 1),
        "masteryLabel": label,
        "masteryCode": code,
        "eligible": scoring.is_eligible(mastery),
    }


def abandon_cycle(conn: sqlite3.Connection, cycle_id: int) -> None:
    cycle = _cycle_row(conn, cycle_id)
    if cycle["finished_at"] is not None:
        raise CycleError("cycle_finished", "这个循环已经完成了", status=409)
    conn.execute("DELETE FROM cycles WHERE id = ?", (cycle_id,))


def _ensure_finished(conn: sqlite3.Connection, cycle_id: int) -> sqlite3.Row:
    cycle = _cycle_row(conn, cycle_id)
    if cycle["finished_at"] is None:
        raise CycleError("cycle_not_finished", "循环还没完成，暂时没有回顾卡片", status=409)
    return cycle


def review_cards(conn: sqlite3.Connection, cycle_id: int) -> list[dict[str, Any]]:
    """循环结束后，把本轮里熟练度 ≤30 的卡片再列一遍。"""
    _ensure_finished(conn, cycle_id)
    rows = conn.execute(
        """SELECT ci.word_id, ci.card_read, w.term, w.meaning, w.phonetic, w.pos,
                  COALESCE(p.mastery, 0) AS mastery
           FROM cycle_items ci
           JOIN words w ON w.id = ci.word_id
           LEFT JOIN progress p ON p.word_id = ci.word_id
           WHERE ci.cycle_id = ? AND ci.answered = 1 AND COALESCE(p.mastery, 0) <= ?
           ORDER BY COALESCE(p.mastery, 0) ASC, ci.pos ASC""",
        (cycle_id, scoring.REVIEW_CARD_MAX),
    ).fetchall()
    cards = []
    for row in rows:
        mastery = float(row["mastery"])
        label, _ = scoring.mastery_level(mastery)
        cards.append(
            {
                "wordId": int(row["word_id"]),
                "term": row["term"],
                "meaning": row["meaning"],
                "phonetic": row["phonetic"],
                "pos": row["pos"],
                "mastery": round(mastery, 1),
                "masteryLabel": label,
                "cardRead": bool(row["card_read"]),
                "memory": etymology.memory_card(conn, int(row["word_id"])),
            }
        )
    return cards


def mark_card_read(conn: sqlite3.Connection, cycle_id: int, word_id: int) -> dict[str, Any]:
    """回顾卡片点「已读」：熟练度 +10（每个词每轮只加一次）。"""
    _ensure_finished(conn, cycle_id)
    item = conn.execute(
        "SELECT * FROM cycle_items WHERE cycle_id = ? AND word_id = ?", (cycle_id, word_id)
    ).fetchone()
    if item is None or not int(item["answered"]):
        raise CycleError("card_not_found", "没有这张回顾卡片", status=404)
    progress = conn.execute("SELECT * FROM progress WHERE word_id = ?", (word_id,)).fetchone()
    if progress is None:
        raise CycleError("card_not_found", "没有这张回顾卡片", status=404)
    if int(item["card_read"]):
        mastery = float(progress["mastery"])
        return {
            "wordId": word_id,
            "mastery": round(mastery, 1),
            "masteryLabel": scoring.mastery_level(mastery)[0],
            "cardRead": True,
            "gained": 0.0,
        }
    mastery = min(100.0, float(progress["mastery"]) + scoring.CARD_READ_GAIN)
    stamp = util.now_iso()
    conn.execute(
        "UPDATE progress SET mastery = ?, user_mark = ?, updated_at = ? WHERE word_id = ?",
        (mastery, scoring.stage_of(mastery), stamp, word_id),
    )
    conn.execute(
        "UPDATE cycle_items SET card_read = 1 WHERE cycle_id = ? AND word_id = ?", (cycle_id, word_id)
    )
    return {
        "wordId": word_id,
        "mastery": round(mastery, 1),
        "masteryLabel": scoring.mastery_level(mastery)[0],
        "cardRead": True,
        "gained": scoring.CARD_READ_GAIN,
    }


def streak_days(conn: sqlite3.Connection, tz_name: str) -> int:
    rows = conn.execute("SELECT DISTINCT date FROM daily_log ORDER BY date DESC LIMIT 400").fetchall()
    if not rows:
        return 0
    dates = [Date.fromisoformat(str(row["date"])) for row in rows]
    today = Date.fromisoformat(util.today_str(tz_name))
    if (today - dates[0]).days > 1:
        return 0
    count = 1
    previous = dates[0]
    for current in dates[1:]:
        if (previous - current).days == 1:
            count += 1
            previous = current
        else:
            break
    return count


def mastery_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    total = int(conn.execute("SELECT COUNT(*) AS n FROM words").fetchone()["n"])
    learned = int(conn.execute("SELECT COUNT(*) AS n FROM progress WHERE seen > 0").fetchone()["n"])
    rows = conn.execute("SELECT mastery FROM progress WHERE seen > 0").fetchall()
    buckets = {"不认识": 0, "模糊": 0, "认识": 0, "很熟": 0}
    for row in rows:
        label, _ = scoring.mastery_level(float(row["mastery"]))
        buckets[label] += 1
    return {
        "total": total,
        "learned": learned,
        "unseen": total - learned,
        "excluded": int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM progress WHERE mastery > ?", (scoring.MASTERY_EXCLUDE,)
            ).fetchone()["n"]
        ),
        **buckets,
    }


def today_snapshot(conn: sqlite3.Connection, tz_name: str) -> dict[str, Any]:
    day = util.today_str(tz_name)
    settings = get_settings(conn)
    active = active_cycle(conn)
    finished_today = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM cycles WHERE date = ? AND finished_at IS NOT NULL", (day,)
        ).fetchone()["n"]
    )
    today_row = conn.execute(
        """SELECT COUNT(*) AS answered, COALESCE(SUM(correct), 0) AS correct,
                  COALESCE(SUM(response_ms), 0) AS ms
           FROM daily_log WHERE date = ?""",
        (day,),
    ).fetchone()
    answered = int(today_row["answered"])
    correct = int(today_row["correct"])
    pending = int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM annotations WHERE status IN ('pending', 'failed')"
        ).fetchone()["n"]
    )
    annotated = int(
        conn.execute("SELECT COUNT(*) AS n FROM annotations WHERE status = 'ok'").fetchone()["n"]
    )
    recent = conn.execute(
        """SELECT id, date, size, answered, correct, started_at, finished_at
           FROM cycles WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 5"""
    ).fetchall()
    return {
        "date": day,
        "settings": settings,
        "activeCycle": active,
        "today": {
            "cycles": finished_today,
            "answered": answered,
            "correct": correct,
            "accuracy": round(100 * correct / answered, 1) if answered else 0,
            "avgResponseMs": round(today_row["ms"] / answered) if answered else 0,
        },
        "recentCycles": [_cycle_dict(row) for row in recent],
        "totalWords": int(conn.execute("SELECT COUNT(*) AS n FROM words").fetchone()["n"]),
        "eligibleCount": eligible_count(conn),
        "mastery": mastery_distribution(conn),
        "streak": streak_days(conn, tz_name),
        "annotations": {"annotated": annotated, "pending": pending},
    }
