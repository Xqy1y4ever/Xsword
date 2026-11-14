"""测试夹具：临时数据库 + 已登录客户端。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "test-pass-123"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        db_path=str(tmp_path / "test.db"),
        session_secret="a" * 64,
        admin_password_hash=hash_password(PASSWORD),
        dist_dir=str(tmp_path / "no-dist"),
        llm_base_url="",
        llm_model="",
        llm_api_key="",
        timezone="Asia/Shanghai",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture()
def app_client(tmp_path):
    app = create_app(settings=make_settings(tmp_path))
    with TestClient(app) as client:
        yield app, client
    app.state.db.close()


@pytest.fixture()
def client(app_client):
    return app_client[1]


@pytest.fixture()
def app(app_client):
    return app_client[0]


@pytest.fixture()
def auth_client(client):
    response = client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def add_word(client: TestClient, term: str, meaning: str, **extra) -> dict:
    payload = {"term": term, "meaning": meaning, **extra}
    response = client.post("/api/words", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_words(client: TestClient, pairs: list[tuple[str, str]]) -> list[dict]:
    return [add_word(client, term, meaning) for term, meaning in pairs]
