"""词根/词缀库与标注：增量合并、词族查询、记忆卡片数据。"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from typing import Any

from .util import now_iso

MORPHEME_TYPES = ("root", "prefix", "suffix")


def normalize_key(text: str) -> str:
    key = (text or "").strip().lower()
    key = key.replace("—", "-").replace("–", "-").replace("_", "-")
    key = re.sub(r"\s+", " ", key)
    key = key.strip("- ")
    return key


def normalize_type(kind: str) -> str:
    kind = (kind or "root").strip().lower()
    if kind.startswith("pre"):
        return "prefix"
    if kind.startswith("suf"):
        return "suffix"
    return "root"


def upsert_root(conn: sqlite3.Connection, key: str, gloss: str = "", origin: str = "", note: str = "") -> int:
    key = normalize_key(key)
    stamp = now_iso()
    row = conn.execute("SELECT id FROM roots WHERE key = ?", (key,)).fetchone()
    if row:
        conn.execute(
            """UPDATE roots SET
                 gloss = CASE WHEN gloss = '' THEN ? ELSE gloss END,
                 origin = CASE WHEN origin = '' THEN ? ELSE origin END,
                 note = CASE WHEN note = '' THEN ? ELSE note END,
                 usage = usage + 1, updated_at = ?
               WHERE id = ?""",
            (gloss or "", origin or "", note or "", stamp, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO roots(key, gloss, origin, note, usage, created_at, updated_at) VALUES(?,?,?,?,1,?,?)",
        (key, gloss or "", origin or "", note or "", stamp, stamp),
    )
    return int(cur.lastrowid)


def upsert_affix(conn: sqlite3.Connection, key: str, type_: str, gloss: str = "", note: str = "") -> int:
    key = normalize_key(key)
    kind = normalize_type(type_)
    stamp = now_iso()
    row = conn.execute("SELECT id FROM affixes WHERE key = ?", (key,)).fetchone()
    if row:
        conn.execute(
            """UPDATE affixes SET
                 gloss = CASE WHEN gloss = '' THEN ? ELSE gloss END,
                 note = CASE WHEN note = '' THEN ? ELSE note END,
                 usage = usage + 1, updated_at = ?
               WHERE id = ?""",
            (gloss or "", note or "", stamp, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO affixes(key, type, gloss, note, usage, created_at, updated_at) VALUES(?,?,?,?,1,?,?)",
        (key, kind, gloss or "", note or "", stamp, stamp),
    )
    return int(cur.lastrowid)


def roots_context(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT key, gloss, origin FROM roots ORDER BY usage DESC, id ASC LIMIT ?", (limit,)
    ).fetchall()
    return [{"key": r["key"], "gloss": r["gloss"], "origin": r["origin"]} for r in rows]


def affixes_context(conn: sqlite3.Connection, limit: int = 120) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT key, type, gloss FROM affixes ORDER BY usage DESC, id ASC LIMIT ?", (limit,)
    ).fetchall()
    return [{"key": r["key"], "type": r["type"], "gloss": r["gloss"]} for r in rows]


def find_word_id(conn: sqlite3.Connection, term: str) -> int | None:
    row = conn.execute("SELECT id FROM words WHERE lower(term) = lower(?)", (term.strip(),)).fetchone()
    return int(row["id"]) if row else None


def replace_word_morphemes(
    conn: sqlite3.Connection, word_id: int, breakdown: list[dict[str, Any]]
) -> dict[str, int]:
    """按标注结果重建该词的词根/词缀关联（幂等）。"""
    conn.execute("DELETE FROM word_roots WHERE word_id = ?", (word_id,))
    conn.execute("DELETE FROM word_affixes WHERE word_id = ?", (word_id,))
    stats = {"roots": 0, "affixes": 0}
    for pos, item in enumerate(breakdown or []):
        form = (item.get("form") or "").strip()
        kind = normalize_type(item.get("type") or "root")
        key = normalize_key(item.get("key") or form)
        gloss = (item.get("gloss") or "").strip()
        note = (item.get("note") or "").strip()
        origin = (item.get("origin") or "").strip()
        if kind == "root":
            root_id = upsert_root(conn, key, gloss, origin, note)
            conn.execute(
                "INSERT OR IGNORE INTO word_roots(word_id, root_id, form, pos) VALUES(?,?,?,?)",
                (word_id, root_id, form or key, pos),
            )
            stats["roots"] += 1
        else:
            affix_id = upsert_affix(conn, key, kind, gloss, note)
            conn.execute(
                "INSERT OR IGNORE INTO word_affixes(word_id, affix_id, form) VALUES(?,?,?)",
                (word_id, affix_id, form or key),
            )
            stats["affixes"] += 1
    return stats


def replace_word_links(
    conn: sqlite3.Connection,
    word_id: int,
    cognates: list[str] | None = None,
    derivatives: list[str] | None = None,
    confusables: list[str] | None = None,
) -> int:
    conn.execute("DELETE FROM word_links WHERE word_id = ?", (word_id,))
    written = 0
    groups = (
        ("cognate", cognates or []),
        ("derivative", derivatives or []),
        ("confusable", confusables or []),
    )
    for relation, terms in groups:
        for term in terms:
            term = (term or "").strip()
            if not term:
                continue
            related_id = None if relation == "confusable" else find_word_id(conn, term)
            conn.execute(
                "INSERT OR IGNORE INTO word_links(word_id, related_term, relation, related_word_id) VALUES(?,?,?,?)",
                (word_id, term, relation, related_id),
            )
            written += 1
    return written


def save_annotation(
    conn: sqlite3.Connection,
    word_id: int,
    payload: dict[str, Any],
    *,
    source: str = "llm",
    model: str = "",
    prompt_version: str = "",
    status: str = "ok",
    error: str = "",
) -> dict[str, int]:
    """写入一条标注并同步词根/词缀/关联，全部幂等。"""
    breakdown = payload.get("breakdown") or []
    if not isinstance(breakdown, list):
        breakdown = []
    mnemonic = str(payload.get("mnemonic") or "").strip()
    cognates = [str(x) for x in (payload.get("cognates") or []) if str(x).strip()]
    derivatives = [str(x) for x in (payload.get("derivatives") or []) if str(x).strip()]
    confusables = [str(x) for x in (payload.get("confusables") or []) if str(x).strip()]

    conn.execute(
        """INSERT INTO annotations(word_id, breakdown_json, mnemonic, cognates_text, derivatives_text,
                                   confusables_text, source, model, prompt_version, status, error, updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(word_id) DO UPDATE SET
             breakdown_json = excluded.breakdown_json,
             mnemonic = CASE WHEN excluded.mnemonic = '' THEN annotations.mnemonic ELSE excluded.mnemonic END,
             cognates_text = excluded.cognates_text,
             derivatives_text = excluded.derivatives_text,
             confusables_text = excluded.confusables_text,
             source = excluded.source,
             model = excluded.model,
             prompt_version = excluded.prompt_version,
             status = excluded.status,
             error = excluded.error,
             updated_at = excluded.updated_at""",
        (
            word_id,
            json.dumps(breakdown, ensure_ascii=False),
            mnemonic,
            ", ".join(cognates),
            ", ".join(derivatives),
            " | ".join(confusables),
            source,
            model,
            prompt_version,
            status,
            error,
            now_iso(),
        ),
    )
    morphemes = replace_word_morphemes(conn, word_id, breakdown)
    links = replace_word_links(conn, word_id, cognates, derivatives, confusables)
    return {"roots": morphemes["roots"], "affixes": morphemes["affixes"], "links": links}


def mark_annotation_pending(conn: sqlite3.Connection, word_id: int, error: str = "") -> None:
    conn.execute(
        """INSERT INTO annotations(word_id, source, status, error, updated_at)
           VALUES(?, 'llm', 'pending', ?, ?)
           ON CONFLICT(word_id) DO UPDATE SET status = 'pending', error = excluded.error,
             updated_at = excluded.updated_at""",
        (word_id, error, now_iso()),
    )


def annotation_status(conn: sqlite3.Connection, word_id: int) -> str:
    row = conn.execute("SELECT status FROM annotations WHERE word_id = ?", (word_id,)).fetchone()
    return row["status"] if row else "missing"


def _split_text_list(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[,，;；|]", text)
    return [p.strip() for p in parts if p.strip()]


def word_morphemes(conn: sqlite3.Connection, word_id: int) -> dict[str, Any]:
    root_rows = conn.execute(
        """SELECT r.id, r.key, r.gloss, r.origin, wr.form, wr.pos
           FROM word_roots wr JOIN roots r ON r.id = wr.root_id
           WHERE wr.word_id = ? ORDER BY wr.pos""",
        (word_id,),
    ).fetchall()
    affix_rows = conn.execute(
        """SELECT a.id, a.key, a.type, a.gloss, wa.form
           FROM word_affixes wa JOIN affixes a ON a.id = wa.affix_id
           WHERE wa.word_id = ?""",
        (word_id,),
    ).fetchall()
    return {
        "roots": [dict(r) for r in root_rows],
        "affixes": [dict(r) for r in affix_rows],
    }


def word_family(conn: sqlite3.Connection, word_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """与本词共享词根的其他词（同根词），不依赖模型。"""
    rows = conn.execute(
        """SELECT DISTINCT w.id, w.term, w.meaning, COALESCE(p.mastery, 0) AS mastery
           FROM word_roots me
           JOIN word_roots wr ON wr.root_id = me.root_id AND wr.word_id != me.word_id
           JOIN words w ON w.id = wr.word_id
           LEFT JOIN progress p ON p.word_id = w.id
           WHERE me.word_id = ?
           ORDER BY mastery ASC, w.id ASC
           LIMIT ?""",
        (word_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def word_links(conn: sqlite3.Connection, word_id: int) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        "SELECT related_term, relation, related_word_id FROM word_links WHERE word_id = ?",
        (word_id,),
    ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {"cognates": [], "derivatives": [], "confusables": []}
    for r in rows:
        bucket = {"cognate": "cognates", "derivative": "derivatives", "confusable": "confusables"}[
            r["relation"]
        ]
        out[bucket].append({"term": r["related_term"], "wordId": r["related_word_id"]})
    return out


def memory_card(conn: sqlite3.Connection, word_id: int) -> dict[str, Any]:
    """记忆卡片数据：拆解、词根词缀、同根词、衍生词、联想。"""
    word = conn.execute("SELECT * FROM words WHERE id = ?", (word_id,)).fetchone()
    if word is None:
        return {}
    ann = conn.execute("SELECT * FROM annotations WHERE word_id = ?", (word_id,)).fetchone()
    morphemes = word_morphemes(conn, word_id)
    links = word_links(conn, word_id)
    family = word_family(conn, word_id)
    breakdown: list[dict[str, Any]] = []
    if ann is not None:
        try:
            breakdown = json.loads(ann["breakdown_json"] or "[]")
        except json.JSONDecodeError:
            breakdown = []
    return {
        "wordId": word_id,
        "term": word["term"],
        "meaning": word["meaning"],
        "phonetic": word["phonetic"],
        "pos": word["pos"],
        "breakdown": breakdown,
        "roots": morphemes["roots"],
        "affixes": morphemes["affixes"],
        "mnemonic": ann["mnemonic"] if ann else "",
        "cognates": links["cognates"],
        "derivatives": links["derivatives"],
        "confusables": links["confusables"],
        "sameRootWords": family,
        "source": ann["source"] if ann else "",
        "status": ann["status"] if ann else "missing",
        "updatedAt": ann["updated_at"] if ann else "",
    }
