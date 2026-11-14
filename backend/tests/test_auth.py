"""鉴权与会话测试。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from tests.conftest import PASSWORD, make_settings


def test_api_requires_login(client):
    assert client.get("/api/today").status_code == 401
    assert client.get("/api/words").status_code == 401
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/auth/me").json() == {"authenticated": False}


def test_login_success_and_me(client):
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200
    assert "vocab_session" in response.cookies
    assert client.get("/api/auth/me").json() == {"authenticated": True}
    assert client.get("/api/today").status_code == 200


def test_login_wrong_password(client):
    response = client.post("/api/auth/login", json={"password": "wrong-pass"})
    assert response.status_code == 401
    assert response.json()["error"] == "bad_password"


def test_logout(client):
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").json() == {"authenticated": False}


def test_login_rate_limited(client):
    for _ in range(8):
        assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"password": "nope"})
    assert blocked.status_code == 429
    assert blocked.json()["error"] == "too_many_attempts"


def test_login_without_password_configured(tmp_path):
    app = create_app(settings=make_settings(tmp_path, admin_password_hash=""))
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"password": "anything"})
        assert response.status_code == 503
        assert response.json()["error"] == "password_not_set"
    app.state.db.close()


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["passwordConfigured"] is True
