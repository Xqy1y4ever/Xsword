"""大模型配置：数据库存储、Key 脱敏、连通性测试。"""
from __future__ import annotations

import json

import httpx

from app import llm_config

from tests.conftest import add_word


def test_llm_config_requires_auth(client):
    assert client.get("/api/llm-config").status_code == 401


def test_default_config_is_disabled(auth_client):
    body = auth_client.get("/api/llm-config").json()
    assert body["enabled"] is False
    assert body["apiKeySet"] is False
    assert body["baseUrl"] == ""
    assert body["model"] == ""


def test_save_config_masks_api_key(auth_client, client):
    response = auth_client.put(
        "/api/llm-config",
        json={"baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-secret-1234", "model": "deepseek-chat", "batchSize": 8},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["baseUrl"] == "https://api.deepseek.com/v1"
    assert body["model"] == "deepseek-chat"
    assert body["apiKeySet"] is True
    assert body["apiKeyHint"] == "…1234"
    assert "sk-secret-1234" not in response.text

    fetched = auth_client.get("/api/llm-config").json()
    assert fetched["apiKeySet"] is True
    assert "sk-secret-1234" not in json.dumps(fetched, ensure_ascii=False)

    health = client.get("/api/health").json()
    assert health["llmEnabled"] is True
    assert health["llmModel"] == "deepseek-chat"


def test_partial_update_keeps_key_and_clear_key(auth_client):
    auth_client.put(
        "/api/llm-config",
        json={"baseUrl": "https://api.example.com/v1", "apiKey": "sk-abcdef", "model": "m1"},
    )
    updated = auth_client.put("/api/llm-config", json={"model": "m2"}).json()
    assert updated["model"] == "m2"
    assert updated["apiKeySet"] is True  # 不传 apiKey 时保留原 Key

    cleared = auth_client.put("/api/llm-config", json={"apiKey": ""}).json()
    assert cleared["apiKeySet"] is False
    assert cleared["enabled"] is True  # Key 清空但仍配置了地址与模型


def test_clear_base_url_disables(auth_client):
    auth_client.put(
        "/api/llm-config", json={"baseUrl": "https://api.example.com/v1", "model": "m1", "apiKey": "k"}
    )
    body = auth_client.put("/api/llm-config", json={"baseUrl": ""}).json()
    assert body["baseUrl"] == ""
    assert body["enabled"] is False


def test_reject_invalid_base_url(auth_client):
    response = auth_client.put("/api/llm-config", json={"baseUrl": "api.example.com/v1"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_base_url"


def test_test_endpoint_without_config(auth_client):
    response = auth_client.post("/api/llm-config/test")
    assert response.status_code == 400
    assert response.json()["error"] == "llm_not_configured"


def test_test_endpoint_with_mock_transport(auth_client, app):
    auth_client.put(
        "/api/llm-config",
        json={"baseUrl": "http://llm.local/v1", "apiKey": "sk-test", "model": "test-model"},
    )
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})

    app.state.llm_transport = httpx.MockTransport(handler)
    try:
        response = auth_client.post("/api/llm-config/test")
    finally:
        app.state.llm_transport = None
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["sample"] == "pong"
    assert body["latencyMs"] >= 0
    assert captured["url"].endswith("/v1/chat/completions")


def test_test_endpoint_reports_unreachable(auth_client, app):
    auth_client.put(
        "/api/llm-config",
        json={"baseUrl": "http://llm.local/v1", "model": "test-model"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    app.state.llm_transport = httpx.MockTransport(handler)
    try:
        response = auth_client.post("/api/llm-config/test")
    finally:
        app.state.llm_transport = None
    assert response.status_code == 502
    assert response.json()["error"] == "llm_unreachable"


def test_new_word_auto_enqueues_and_annotates(auth_client, app):
    auth_client.put(
        "/api/llm-config",
        json={"baseUrl": "http://llm.local/v1", "model": "test-model", "apiKey": "sk-test"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        items = [
            {
                "word": "sustain",
                "breakdown": [{"form": "tain", "type": "root", "key": "tain", "gloss": "握持"}],
                "mnemonic": "sus-（在下）+ tain（握住）→ 从下面撑住 → 维持",
                "cognates": ["retain"],
            }
        ]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps({"items": items}, ensure_ascii=False)}}]}
        )

    app.state.llm_transport = httpx.MockTransport(handler)
    try:
        created = auth_client.post("/api/words", json={"term": "sustain", "meaning": "维持"})
    finally:
        app.state.llm_transport = None
    assert created.status_code == 201
    detail = auth_client.get(f"/api/words/{created.json()['id']}").json()
    assert detail["annotationStatus"] == "ok"
    card = auth_client.get(f"/api/words/{created.json()['id']}/annotation").json()
    assert card["source"] == "llm"
    assert card["status"] == "ok"


def test_bootstrap_from_env_only_once(tmp_path):
    from app.db import Database

    db = Database(str(tmp_path / "boot.db"))
    db.migrate()

    class Legacy:
        llm_base_url = "http://legacy.local/v1"
        llm_api_key = "sk-legacy"
        llm_model = "legacy-model"
        llm_batch_size = 5

    conn = db.conn()
    assert llm_config.bootstrap_from_env(conn, Legacy()) is True
    first = llm_config.get_config(conn)
    assert first.base_url == "http://legacy.local/v1"
    assert first.model == "legacy-model"
    assert first.batch_size == 5

    # 第二次不再覆盖（数据库为准）
    assert llm_config.bootstrap_from_env(conn, Legacy()) is False
    db.close()
