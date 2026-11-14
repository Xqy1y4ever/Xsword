"""通用时间工具：统一 Asia/Shanghai 自然日。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def now(tz_name: str = "Asia/Shanghai") -> datetime:
    return datetime.now(tz(tz_name))


def now_iso(tz_name: str = "Asia/Shanghai") -> str:
    return now(tz_name).isoformat(timespec="seconds")


def today_str(tz_name: str = "Asia/Shanghai") -> str:
    return now(tz_name).date().isoformat()


def yesterday_str(tz_name: str = "Asia/Shanghai") -> str:
    return (now(tz_name).date() - timedelta(days=1)).isoformat()


def days_ago_str(days: int, tz_name: str = "Asia/Shanghai") -> str:
    return (now(tz_name).date() - timedelta(days=days)).isoformat()


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
