"""抽题与判分。"""
from __future__ import annotations

import random
import re
import sqlite3
from typing import Any

MODES = ("en2cn", "cn2en")

_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015"
_APOSTROPHES = "\u2018\u2019\u02bc\u0060"
_EDGE_PUNCT = " \t\r\n.,!?;:，。！？；：、\"'“”‘’()（）[]【】"


def normalize_answer(text: str) -> str:
    value = (text or "").strip().lower()
    for dash in _DASHES:
        value = value.replace(dash, "-")
    for apostrophe in _APOSTROPHES:
        value = value.replace(apostrophe, "'")
    value = re.sub(r"\s+", " ", value)
    value = value.strip(_EDGE_PUNCT)
    return value


def acceptable_answers(word: sqlite3.Row | dict[str, Any]) -> list[str]:
    term = str(word["term"])
    alternatives = str(word["alt"] or "")
    answers = [term]
    for part in re.split(r"[,，;；/|]", alternatives):
        part = part.strip()
        if part:
            answers.append(part)
    return list(dict.fromkeys(normalize_answer(a) for a in answers if normalize_answer(a)))


def is_correct(word: sqlite3.Row | dict[str, Any], answer: str) -> bool:
    parsed = [part.strip() for part in re.split(r"[,，;；/|]", answer) if part.strip()]
    normalized = normalize_answer(answer)
    if not normalized:
        return False
    candidates = acceptable_answers(word)
    if normalized in candidates:
        return True
    # 允许多个答案一起提交，只要有一个命中
    return any(normalize_answer(part) in candidates for part in parsed)


def hint_for(term: str) -> str:
    """拼写提示：每个单词首字母 + 剩余下划线 + 总长度。"""
    parts = term.split()
    shown = " ".join(p[0] + "·" * (len(p) - 1) for p in parts if p)
    letters = sum(len(p) for p in parts)
    return f"{shown}（{letters} 个字母）"


def _unique_meanings(conn: sqlite3.Connection, exclude_word_id: int, exclude_meaning: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT meaning FROM words WHERE id != ? AND lower(meaning) != lower(?) ORDER BY random()",
        (exclude_word_id, exclude_meaning),
    ).fetchall()
    seen: list[str] = []
    for row in rows:
        value = str(row["meaning"]).strip()
        if value and value.lower() not in {s.lower() for s in seen}:
            seen.append(value)
    return seen


def build_question(
    conn: sqlite3.Connection,
    word: sqlite3.Row,
    mode: str,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    rng = rng or random.Random()
    if mode == "en2cn":
        distractors = _unique_meanings(conn, int(word["id"]), str(word["meaning"]))
        chosen = distractors[:3]
        options = [str(word["meaning"]), *chosen]
        rng.shuffle(options)
        return {
            "wordId": int(word["id"]),
            "mode": mode,
            "prompt": str(word["term"]),
            "phonetic": str(word["phonetic"] or ""),
            "wordPos": str(word["pos"] or ""),
            "options": options,
            "hint": "",
        }
    return {
        "wordId": int(word["id"]),
        "mode": mode,
        "prompt": str(word["meaning"]),
        "phonetic": "",
        "wordPos": str(word["pos"] or ""),
        "options": None,
        "hint": hint_for(str(word["term"])),
    }


def build_questions(
    conn: sqlite3.Connection,
    words: list[sqlite3.Row],
    mode: str,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    if mode not in MODES:
        raise ValueError(f"未知模式：{mode}")
    if mode == "en2cn":
        total = conn.execute("SELECT COUNT(*) AS n FROM words").fetchone()["n"]
        if int(total) < 2:
            raise ValueError("need_more_words")
    return [build_question(conn, word, mode, rng) for word in words]
