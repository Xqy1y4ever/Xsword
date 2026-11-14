"""SQLite 数据层：连接管理、迁移、事务辅助。"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- 大模型接口配置（单行，运行时以数据库为准；.env 仅用于首次启动引导导入）
CREATE TABLE IF NOT EXISTS llm_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    batch_size INTEGER NOT NULL DEFAULT 20,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT NOT NULL,
    meaning TEXT NOT NULL,
    alt TEXT NOT NULL DEFAULT '',
    phonetic TEXT NOT NULL DEFAULT '',
    pos TEXT NOT NULL DEFAULT '',
    example TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_words_term_lower ON words(lower(term));

CREATE TABLE IF NOT EXISTS progress (
    word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    seen INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    wrong INTEGER NOT NULL DEFAULT 0,
    streak INTEGER NOT NULL DEFAULT 0,
    fast_count INTEGER NOT NULL DEFAULT 0,
    slow_count INTEGER NOT NULL DEFAULT 0,
    speed_score_sum REAL NOT NULL DEFAULT 0,
    user_mark INTEGER NOT NULL DEFAULT 0,
    first_seen_date TEXT,
    last_seen_at TEXT,
    last_result TEXT,
    mastery REAL NOT NULL DEFAULT 0,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_progress_first_seen ON progress(first_seen_date);
CREATE INDEX IF NOT EXISTS idx_progress_mastery ON progress(mastery);

CREATE TABLE IF NOT EXISTS daily_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    phase TEXT NOT NULL,
    correct INTEGER NOT NULL,
    response_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_log_date ON daily_log(date);
CREATE INDEX IF NOT EXISTS idx_daily_log_word ON daily_log(word_id);

-- 循环制练习：每轮由用户设定词数，循环内单词不重复
CREATE TABLE IF NOT EXISTS cycle_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    size INTEGER NOT NULL DEFAULT 20,
    choice_ratio REAL NOT NULL DEFAULT 0.6,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    size INTEGER NOT NULL,
    answered INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cycles_date ON cycles(date);
CREATE INDEX IF NOT EXISTS idx_cycles_open ON cycles(finished_at);

CREATE TABLE IF NOT EXISTS cycle_items (
    cycle_id INTEGER NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    pos INTEGER NOT NULL,
    mode TEXT NOT NULL,
    mastery_at_start REAL NOT NULL DEFAULT 0,
    mastery_before REAL,
    answered INTEGER NOT NULL DEFAULT 0,
    correct INTEGER,
    response_ms INTEGER,
    action TEXT,
    adjust_choice TEXT,
    answered_at TEXT,
    card_read INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (cycle_id, word_id)
);
CREATE INDEX IF NOT EXISTS idx_cycle_items_pending ON cycle_items(cycle_id, answered, pos);

CREATE TABLE IF NOT EXISTS roots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    gloss TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    usage INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS affixes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('prefix', 'suffix')),
    gloss TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    usage INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS word_roots (
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
    form TEXT NOT NULL DEFAULT '',
    pos INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (word_id, root_id, form)
);

CREATE TABLE IF NOT EXISTS word_affixes (
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    affix_id INTEGER NOT NULL REFERENCES affixes(id) ON DELETE CASCADE,
    form TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (word_id, affix_id, form)
);

CREATE TABLE IF NOT EXISTS annotations (
    word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
    breakdown_json TEXT NOT NULL DEFAULT '[]',
    mnemonic TEXT NOT NULL DEFAULT '',
    cognates_text TEXT NOT NULL DEFAULT '',
    derivatives_text TEXT NOT NULL DEFAULT '',
    confusables_text TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'llm',
    model TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok',
    error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS word_links (
    word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    related_term TEXT NOT NULL,
    relation TEXT NOT NULL,
    related_word_id INTEGER,
    PRIMARY KEY (word_id, related_term, relation)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""


class ConnectionProxy:
    """惰性绑定到「当前执行线程」的数据库连接代理。

    FastAPI 会把同步依赖函数和同步接口函数分别丢进线程池，二者可能落在不同线程；
    如果依赖里直接返回 sqlite3.Connection，接口在另一个线程使用它就会抛
    ProgrammingError（SQLite 连接不能跨线程）。这里把取连接的时机推迟到真正执行 SQL 时，
    从而保证连接始终属于执行 SQL 的那个线程。
    """

    __slots__ = ("_database", "_active")

    def __init__(self, database: "Database"):
        self._database = database
        self._active = None

    def _connection(self) -> sqlite3.Connection:
        return self._database.conn()

    # 显式代理常用方法，避免依赖 __getattr__ 的边界情况
    def execute(self, sql: str, parameters=()):
        return self._connection().execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters):
        return self._connection().executemany(sql, seq_of_parameters)

    def executescript(self, script: str):
        return self._connection().executescript(script)

    def commit(self) -> None:
        self._connection().commit()

    def rollback(self) -> None:
        self._connection().rollback()

    def __enter__(self) -> "ConnectionProxy":
        self._active = self._connection()
        self._active.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        active, self._active = self._active, None
        if active is None:
            return False
        return active.__exit__(exc_type, exc, tb)

    def __getattr__(self, name):
        return getattr(self._connection(), name)


class Database:
    """每个线程一个 SQLite 连接；WAL + busy_timeout 支持少量并发读写。"""

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    def conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=3000")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def proxy(self) -> ConnectionProxy:
        """给 Web 请求用的跨线程安全代理。"""
        return ConnectionProxy(self)

    def migrate(self) -> None:
        conn = self.conn()
        with conn:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            else:
                conn.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),)
                )
            conn.execute("INSERT OR IGNORE INTO cycle_settings(id, size) VALUES(1, 20)")
            # 旧库补列：选义/拼写比例（默认 60% 选义）
            setting_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(cycle_settings)").fetchall()
            }
            if "choice_ratio" not in setting_columns:
                conn.execute(
                    "ALTER TABLE cycle_settings ADD COLUMN choice_ratio REAL NOT NULL DEFAULT 0.6"
                )
            # 旧库补列：循环回顾卡片的「已读」标记
            columns = {row[1] for row in conn.execute("PRAGMA table_info(cycle_items)").fetchall()}
            if "card_read" not in columns:
                conn.execute(
                    "ALTER TABLE cycle_items ADD COLUMN card_read INTEGER NOT NULL DEFAULT 0"
                )
            if "mastery_before" not in columns:
                conn.execute("ALTER TABLE cycle_items ADD COLUMN mastery_before REAL")
            if "adjust_choice" not in columns:
                conn.execute("ALTER TABLE cycle_items ADD COLUMN adjust_choice TEXT")
            # 旧库补列：单词词性（n. / v. / adj. …）
            word_columns = {row[1] for row in conn.execute("PRAGMA table_info(words)").fetchall()}
            if "pos" not in word_columns:
                conn.execute("ALTER TABLE words ADD COLUMN pos TEXT NOT NULL DEFAULT ''")

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn()
        with conn:
            yield conn
