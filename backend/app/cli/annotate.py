"""运行词源标注流水线（大模型配置在数据库里，通过设置页或 API 维护）。

用法：
  npm run annotate -- --limit 20
  npm run annotate -- --words 1,2,3
"""
from __future__ import annotations

import argparse
import json
import sys

from .. import llm_config, pipeline
from ..config import get_settings
from ..db import Database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行词源标注流水线")
    parser.add_argument("--db", default=None, help="数据库路径（默认取配置）")
    parser.add_argument("--words", default="", help="指定单词 id，逗号分隔")
    parser.add_argument("--limit", type=int, default=20, help="处理排队任务的上限")
    parser.add_argument(
        "--missing", type=int, default=0, help="把还没有标注的词补标注，最多处理 N 个"
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    db = Database(args.db or settings.db_path)
    db.migrate()
    config = llm_config.get_config(db.conn())
    if not config.enabled:
        print("数据库里还没有可用的大模型配置。", file=sys.stderr)
        print("请在应用「设置 → 词源标注模型」里填写 Base URL 与模型名，", file=sys.stderr)
        print("或 PUT /api/llm-config。也可用 npm run seed 导入离线标注。", file=sys.stderr)
        return 2

    print(f"使用模型：{config.model}（{config.base_url}）", file=sys.stderr)
    if args.missing:
        conn = db.conn()
        rows = conn.execute(
            """SELECT w.id FROM words w
               LEFT JOIN annotations a ON a.word_id = w.id
               WHERE a.status IS NULL OR a.status <> 'ok'
               ORDER BY w.id LIMIT ?""",
            (args.missing,),
        ).fetchall()
        word_ids = [int(row["id"]) for row in rows]
        print(f"待补标注：{len(word_ids)} 个词", file=sys.stderr)
        result = pipeline.annotate_words(db, word_ids)
    elif args.words:
        ids = [int(part) for part in args.words.split(",") if part.strip().isdigit()]
        result = pipeline.annotate_words(db, ids)
    else:
        result = pipeline.process_pending(db, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
