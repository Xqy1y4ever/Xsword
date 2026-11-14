"""给词库补词性（part of speech），存 words.pos。

用法：
  node scripts/py.mjs -m app.cli.pos                 # 补齐所有 pos 为空的词
  node scripts/py.mjs -m app.cli.pos --missing 100   # 只补 100 个
  node scripts/py.mjs -m app.cli.pos --export        # 补完后导出 seed/pos.json
  node scripts/py.mjs -m app.cli.pos --dry-run       # 只看有多少词缺词性
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import llm, llm_config
from ..config import get_settings
from ..db import Database

ROOT = Path(__file__).resolve().parents[3]
POS_SEED = ROOT / "seed" / "pos.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="补齐单词词性")
    parser.add_argument("--db", default=None, help="数据库路径（默认取配置）")
    parser.add_argument("--missing", type=int, default=5000, help="最多处理多少个缺词性的词")
    parser.add_argument("--batch", type=int, default=40, help="每次请求多少个词（1–50）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不请求模型")
    parser.add_argument("--export", action="store_true", help="处理完后导出 seed/pos.json")
    args = parser.parse_args(argv)

    db = Database(args.db or get_settings().db_path)
    db.migrate()
    conn = db.conn()
    config = llm_config.get_config(conn)

    rows = conn.execute(
        "SELECT id, term, meaning FROM words WHERE pos = '' ORDER BY id LIMIT ?",
        (max(0, args.missing),),
    ).fetchall()
    if args.dry_run:
        print(json.dumps({"missing": len(rows), "llmEnabled": config.enabled}, ensure_ascii=False))
        return 0
    if not rows:
        print(json.dumps({"missing": 0, "processed": 0, "updated": 0}, ensure_ascii=False))
        return 0
    if not config.enabled:
        raise SystemExit("大模型未配置：先在设置页填写 Base URL / 模型名")

    batch_size = max(1, min(50, args.batch))
    processed = updated = failed = 0
    errors: list[str] = []
    for start in range(0, len(rows), batch_size):
        chunk = rows[start : start + batch_size]
        words = [{"term": str(row["term"]), "meaning": str(row["meaning"])} for row in chunk]
        try:
            items = llm.annotate_pos_batch(config, words)
        except llm.LLMError as exc:
            failed += len(chunk)
            errors.append(str(exc)[:200])
            continue
        by_term = {item["word"].strip().lower(): item["pos"] for item in items}
        to_update = [
            (by_term[str(row["term"]).strip().lower()], int(row["id"]))
            for row in chunk
            if str(row["term"]).strip().lower() in by_term
        ]
        processed += len(chunk)
        updated += len(to_update)
        if to_update:
            with conn:
                for pos, word_id in to_update:
                    conn.execute("UPDATE words SET pos = ? WHERE id = ?", (pos, word_id))

    result = {"missing": len(rows), "processed": processed, "updated": updated, "failed": failed}
    if errors:
        result["errors"] = errors[:5]
    if args.export:
        exported = export_pos(conn)
        result["exported"] = exported
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def export_pos(conn) -> int:
    rows = conn.execute("SELECT term, pos FROM words WHERE pos != '' ORDER BY lower(term)").fetchall()
    payload = {str(row["term"]): str(row["pos"]) for row in rows}
    POS_SEED.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(payload)


if __name__ == "__main__":
    raise SystemExit(main())
