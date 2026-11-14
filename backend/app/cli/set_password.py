"""生成口令哈希，可选写入 .env（同时补齐 SESSION_SECRET）。

用法：
  npm run set-password -- 你的口令
  npm run set-password -- 你的口令 --write
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import sys
from pathlib import Path

from ..security import hash_password

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def _upsert_env(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    if pattern.search(text):
        return pattern.sub(f"{key}={value}", text, count=1)
    return text.rstrip("\n") + f"\n{key}={value}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成背单词应用的登录口令哈希")
    parser.add_argument("password", nargs="?", help="口令（不填则交互输入）")
    parser.add_argument("--write", action="store_true", help="写入项目根 .env")
    args = parser.parse_args(argv)

    password = args.password or getpass.getpass("输入新口令：")
    if len(password) < 6:
        print("口令至少 6 位。", file=sys.stderr)
        return 1
    if not args.password:
        confirm = getpass.getpass("再次输入口令：")
        if confirm != password:
            print("两次输入不一致。", file=sys.stderr)
            return 1

    digest = hash_password(password)
    print(f"ADMIN_PASSWORD_HASH={digest}")

    if args.write:
        if ENV_FILE.exists():
            text = ENV_FILE.read_text(encoding="utf-8")
        elif ENV_EXAMPLE.exists():
            text = ENV_EXAMPLE.read_text(encoding="utf-8")
        else:
            text = ""
        text = _upsert_env(text, "ADMIN_PASSWORD_HASH", digest)
        if not re.search(r"^SESSION_SECRET=\S", text, re.MULTILINE):
            text = _upsert_env(text, "SESSION_SECRET", secrets.token_hex(32))
        ENV_FILE.write_text(text, encoding="utf-8")
        print(f"已写入 {ENV_FILE}")
    else:
        print("把上面这行写入 .env（或加 --write 自动写入）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
