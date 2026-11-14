"""一次性数据迁移：把点过自评（user_mark>0）的词，熟练度改成对应档位分数。

自评四档分数：不认识 15 / 模糊 30 / 认识 45 / 很熟 60。
已掌握（>90）的词不动，避免把拼写「已熟练」的词从 95 拉低。

用法：
  node scripts/py.mjs -m app.cli.migrate_marks
  node scripts/py.mjs -m app.cli.migrate_marks --dry-run
"""
from __future__ import annotations

import argparse
import json

from .. import scoring, util
from ..config import get_settings
from ..db import Database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按自评标签重设熟练度")
    parser.add_argument("--db", default=None, help="数据库路径（默认取配置）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    args = parser.parse_args(argv)

    settings = get_settings()
    db = Database(args.db or settings.db_path)
    db.migrate()
    conn = db.conn()

    rows = conn.execute(
        """SELECT p.word_id, p.user_mark, p.mastery, w.term
           FROM progress p JOIN words w ON w.id = p.word_id
           WHERE p.user_mark BETWEEN 1 AND 4 AND p.mastery < ?""",
        (scoring.MASTERY_EXCLUDE,),
    ).fetchall()

    changes = []
    for row in rows:
        anchor = scoring.mark_anchor(int(row["user_mark"]))
        if anchor is None or float(row["mastery"]) == anchor:
            continue
        changes.append(
            {
                "wordId": int(row["word_id"]),
                "term": row["term"],
                "mark": int(row["user_mark"]),
                "before": float(row["mastery"]),
                "after": anchor,
            }
        )

    if not args.dry_run and changes:
        stamp = util.now_iso()
        with conn:
            for item in changes:
                conn.execute(
                    "UPDATE progress SET mastery = ?, updated_at = ? WHERE word_id = ?",
                    (item["after"], stamp, item["wordId"]),
                )

    print(
        json.dumps(
            {
                "scanned": len(rows),
                "changed": len(changes),
                "dryRun": bool(args.dry_run),
                "samples": changes[:10],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
