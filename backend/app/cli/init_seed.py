"""导入初始词库、词根词缀库与离线标注（幂等）。

用法：
  npm run seed
  npm run seed -- --file seed/words.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .. import etymology, pipeline
from ..config import get_settings
from ..db import Database
from ..util import now_iso

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = ROOT / "seed"
WORD_FIELDS = ("term", "meaning", "alt", "phonetic", "example", "tags")


def load_json(name: str) -> Any:
    path = SEED_DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def seed_words(conn: sqlite3.Connection, words: list[dict[str, Any]]) -> tuple[int, int]:
    added = skipped = 0
    stamp = now_iso()
    for item in words:
        term = str(item.get("term") or "").strip()
        meaning = str(item.get("meaning") or "").strip()
        if not term or not meaning:
            skipped += 1
            continue
        exists = conn.execute("SELECT id FROM words WHERE lower(term) = lower(?)", (term,)).fetchone()
        if exists:
            skipped += 1
            continue
        conn.execute(
            """INSERT INTO words(term, meaning, alt, phonetic, pos, example, tags, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                term,
                meaning,
                str(item.get("alt") or ""),
                str(item.get("phonetic") or ""),
                str(item.get("pos") or ""),
                str(item.get("example") or ""),
                str(item.get("tags") or ""),
                stamp,
                stamp,
            ),
        )
        added += 1
    return added, skipped


def seed_pos(conn: sqlite3.Connection, pos_map: dict[str, Any]) -> int:
    """把 seed/pos.json 里的词性补到「还没有词性」的词上。"""
    updated = 0
    for term, pos in pos_map.items():
        term = str(term or "").strip()
        value = str(pos or "").strip()
        if not term or not value:
            continue
        cursor = conn.execute(
            "UPDATE words SET pos = ? WHERE lower(term) = lower(?) AND pos = ''", (value, term)
        )
        updated += cursor.rowcount
    return updated


def seed_roots(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, int]:
    roots = payload.get("roots") or []
    affixes = payload.get("affixes") or []
    for item in roots:
        etymology.upsert_root(
            conn,
            str(item.get("key") or ""),
            str(item.get("gloss") or ""),
            str(item.get("origin") or ""),
            str(item.get("note") or ""),
        )
    for item in affixes:
        etymology.upsert_affix(
            conn,
            str(item.get("key") or ""),
            str(item.get("type") or "prefix"),
            str(item.get("gloss") or ""),
            str(item.get("note") or ""),
        )
    return {"roots": len(roots), "affixes": len(affixes)}


DEFAULT_WORD_FILES = ("words.json", "words_extra.json")  # A 级词表暂时下架（--with-nce 可恢复）


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入初始词库与标注")
    parser.add_argument("--db", default=None, help="数据库路径（默认取配置）")
    parser.add_argument(
        "--file",
        default="words.json",
        help="额外优先加载的词表文件名（相对 seed/，默认 words.json；同时加载 words_extra.json）",
    )
    parser.add_argument(
        "--with-nce",
        action="store_true",
        help="同时导入南大《大学英语通用词汇》A 级词表 seed/nce_a.json（该词表暂时下架）",
    )
    parser.add_argument(
        "--no-annotations", action="store_true", help="只导入词库，不重新导入离线标注"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    db = Database(args.db or settings.db_path)
    db.migrate()
    conn = db.conn()

    word_files = [args.file] + [name for name in DEFAULT_WORD_FILES if name != args.file]
    if args.with_nce and "nce_a.json" not in word_files:
        word_files.append("nce_a.json")
    words: list[dict[str, Any]] = []
    loaded: dict[str, int] = {}
    for name in word_files:
        payload = load_json(name)
        if payload is None:
            continue
        loaded[name] = len(payload)
        words.extend(payload)
    roots_payload = load_json("roots.json") or {"roots": [], "affixes": []}
    annotations = [] if args.no_annotations else (load_json("annotations.json") or [])
    pos_map = load_json("pos.json") or {}

    with conn:
        added, skipped = seed_words(conn, words)
        pos_applied = seed_pos(conn, pos_map)
        roots_stats = seed_roots(conn, roots_payload)
        ann_stats = (
            {"ok": 0, "skipped": 0, "errors": []}
            if args.no_annotations
            else pipeline.import_annotations(conn, annotations, source="seed", model="offline-seed")
        )

    total = conn.execute("SELECT COUNT(*) AS n FROM words").fetchone()["n"]
    roots_total = conn.execute("SELECT COUNT(*) AS n FROM roots").fetchone()["n"]
    affix_total = conn.execute("SELECT COUNT(*) AS n FROM affixes").fetchone()["n"]
    annotated = conn.execute(
        "SELECT COUNT(*) AS n FROM annotations WHERE status = 'ok'"
    ).fetchone()["n"]
    print(
        json.dumps(
            {
                "wordsAdded": added,
                "wordsSkipped": skipped,
                "wordsTotal": int(total),
                "posApplied": pos_applied,
                "wordFiles": loaded,
                "roots": roots_stats["roots"],
                "rootsTotal": int(roots_total),
                "affixes": roots_stats["affixes"],
                "affixesTotal": int(affix_total),
                "annotations": ann_stats["ok"],
                "annotationSkipped": ann_stats["skipped"],
                "annotationErrors": ann_stats["errors"],
                "annotatedTotal": int(annotated),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
