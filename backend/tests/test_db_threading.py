"""数据库连接代理的线程安全回归测试（FastAPI 依赖与接口可能在不同线程执行）。"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from app.db import ConnectionProxy, Database


def _make_db(tmp_path) -> Database:
    db = Database(str(tmp_path / "thread.db"))
    db.migrate()
    return db


def test_proxy_works_in_creating_thread(tmp_path):
    db = _make_db(tmp_path)
    proxy = db.proxy()
    assert proxy.execute("SELECT 1").fetchone()[0] == 1
    db.close()


def test_proxy_created_in_one_thread_used_in_another(tmp_path):
    """依赖里创建代理、接口在另一个线程执行 —— 修复前会抛 ProgrammingError。"""
    db = _make_db(tmp_path)
    proxy_created_in_main = db.proxy()

    errors: list[BaseException] = []
    values: list[int] = []

    def endpoint_in_other_thread():
        try:
            with proxy_created_in_main:
                row = proxy_created_in_main.execute("SELECT COUNT(*) FROM words").fetchone()
            values.append(int(row[0]))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=endpoint_in_other_thread)
    thread.start()
    thread.join()

    assert errors == []
    assert values == [0]
    db.close()


def test_proxy_enter_exit_binds_current_thread(tmp_path):
    db = _make_db(tmp_path)
    proxy = db.proxy()

    with proxy:
        proxy.execute("INSERT INTO meta(key, value) VALUES('thread_probe', 'ok')")

    assert proxy.execute("SELECT value FROM meta WHERE key = 'thread_probe'").fetchone()[0] == "ok"
    db.close()


def test_plain_connection_still_rejects_cross_thread_use(tmp_path):
    """说明为什么需要代理：裸连接跨线程会被 sqlite3 拒绝。"""
    db = _make_db(tmp_path)
    conn = db.conn()
    errors: list[BaseException] = []

    def use_raw_connection():
        try:
            conn.execute("SELECT 1").fetchone()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=use_raw_connection)
    thread.start()
    thread.join()

    assert len(errors) == 1
    assert isinstance(errors[0], sqlite3.ProgrammingError)
    db.close()
