"""标注流水线：上下文携带、增量词根、失败降级。"""
from __future__ import annotations

import json

import httpx

from app import llm_config, pipeline

from tests.conftest import add_word


def _set_llm(app, **overrides):
    values = {"base_url": "http://llm.local/v1", "api_key": "sk-test", "model": "test-model"}
    values.update(overrides)
    conn = app.state.db.conn()
    with conn:
        llm_config.save_config(conn, **values)


def test_annotate_without_llm_is_skipped(auth_client, app):
    word = add_word(auth_client, "sustain", "维持")
    result = pipeline.annotate_words(app.state.db, [word["id"]])
    assert result["skipped"] == 1
    assert "未配置" in result["error"]
    status = auth_client.get("/api/annotate/status").json()
    assert status["byStatus"]["pending"] == 1


def test_pipeline_sends_existing_roots_and_writes_increment(auth_client, app):
    pharmacy = add_word(auth_client, "pharmacy", "药房")
    pharmaceutical = add_word(auth_client, "pharmaceutical", "制药的")
    auth_client.post(
        "/api/annotate/import",
        json={
            "items": [
                {
                    "word": "pharmacy",
                    "breakdown": [{"form": "pharm", "type": "root", "key": "pharm", "gloss": "药", "origin": "Greek"}],
                    "mnemonic": "pharm（药）",
                }
            ]
        },
    )
    _set_llm(app)

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured["user"] = body["messages"][1]["content"]
        captured["auth"] = request.headers.get("authorization", "")
        items = [
            {
                "word": "pharmaceutical",
                "breakdown": [
                    {"form": "pharm", "type": "root", "key": "pharm", "gloss": "药", "origin": "Greek"},
                    {"form": "ceutical", "type": "suffix", "key": "ceutical", "gloss": "制备"},
                ],
                "mnemonic": "pharm（药）+ ceutical（制备）→ 制药的",
                "cognates": ["pharmacy"],
                "derivatives": [],
                "confusables": ["pharmacy 药房 vs pharmaceutical 制药的"],
            }
        ]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"items": items}, ensure_ascii=False)}}]}
        )

    transport = httpx.MockTransport(handler)
    result = pipeline.annotate_words(app.state.db, [pharmaceutical["id"]], transport=transport)

    assert result["ok"] == 1
    assert '"pharm"' in captured["user"]  # 已有词根库作为上下文发给拆解器
    assert captured["auth"] == "Bearer sk-test"

    conn = app.state.db.conn()
    root = conn.execute("SELECT * FROM roots WHERE key = 'pharm'").fetchone()
    assert root is not None
    assert root["usage"] >= 2  # 已有词根被复用，usage 累加
    affix = conn.execute("SELECT * FROM affixes WHERE key = 'ceutical'").fetchone()
    assert affix is not None and affix["type"] == "suffix"
    annotation = conn.execute("SELECT * FROM annotations WHERE word_id = ?", (pharmaceutical["id"],)).fetchone()
    assert annotation["status"] == "ok"
    assert annotation["source"] == "llm"
    assert annotation["model"] == "test-model"
    job = conn.execute("SELECT status FROM jobs WHERE id = (SELECT MAX(id) FROM jobs)").fetchone()
    assert job["status"] == "done"

    card = auth_client.get(f"/api/words/{pharmaceutical['id']}/annotation").json()
    assert card["cognates"][0]["wordId"] == pharmacy["id"]
    assert card["sameRootWords"][0]["term"] == "pharmacy"


def test_pipeline_marks_failed_on_bad_response(auth_client, app):
    word = add_word(auth_client, "veto", "否决")
    _set_llm(app)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    result = pipeline.annotate_words(app.state.db, [word["id"]], transport=httpx.MockTransport(handler))
    assert result["failed"] == 1
    conn = app.state.db.conn()
    annotation = conn.execute("SELECT * FROM annotations WHERE word_id = ?", (word["id"],)).fetchone()
    assert annotation["status"] == "failed"
    assert annotation["error"]
