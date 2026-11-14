"""按题型门槛修正「未完成循环」里还没作答的题目（历史数据兼容）。

规则：熟练度 > 50 才可能出拼写；> 60 不再出释义（50–60 两种都可能）。
已完成作答的题目不动（它们已经结算过熟练度）。

用法：
  node scripts/py.mjs -m app.cli.fix_cycle_modes
  node scripts/py.mjs -m app.cli.fix_cycle_modes --dry-run
"""
from __future__ import annotations

import argparse
import json

from ..config import get_settings
from ..db import Database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="修正未完成循环的题型")
    parser.add_argument("--db", default=None, help="数据库路径（默认取配置）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    args = parser.parse_args(argv)

    settings = get_settings()
    db = Database(args.db or settings.db_path)
    db.migrate()
    conn = db.conn()

    rows = conn.execute(
        """SELECT ci.cycle_id, ci.word_id, ci.mode, COALESCE(p.mastery, 0) AS mastery
           FROM cycle_items ci
           JOIN cycles c ON c.id = ci.cycle_id
           LEFT JOIN progress p ON p.word_id = ci.word_id
           WHERE c.finished_at IS NULL AND ci.answered = 0"""
    ).fetchall()

    changes = []
    for row in rows:
        mastery = float(row["mastery"])
        if mastery > 60:
            expected = "cn2en"
        elif mastery <= 50:
            expected = "en2cn"
        else:
            continue  # 50–60 两种都允许
        if row["mode"] != expected:
            changes.append(
                {
                    "cycleId": int(row["cycle_id"]),
                    "wordId": int(row["word_id"]),
                    "mastery": mastery,
                    "before": row["mode"],
                    "after": expected,
                }
            )

    if not args.dry_run and changes:
        with conn:
            for item in changes:
                conn.execute(
                    "UPDATE cycle_items SET mode = ? WHERE cycle_id = ? AND word_id = ?",
                    (item["after"], item["cycleId"], item["wordId"]),
                )

    print(
        json.dumps(
            {"scanned": len(rows), "changed": len(changes), "dryRun": bool(args.dry_run), "items": changes[:20]},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
