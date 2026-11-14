"""静态资源：SPA 回退与缓存头（防止发版后浏览器拿旧 HTML 白屏）。"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

from tests.conftest import make_settings


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root"></div>'
        '<script type="module" src="/assets/app-abc.js"></script></body></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app-abc.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


def test_spa_serves_index_without_cache(tmp_path):
    dist = _make_dist(tmp_path)
    app = create_app(settings=make_settings(tmp_path, dist_dir=str(dist)))
    with TestClient(app) as client:
        for path in ("/", "/practice", "/words/import"):
            response = client.get(path)
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert 'id="root"' in response.text
            assert "no-store" in response.headers["cache-control"]
    app.state.db.close()


def test_hashed_assets_are_immutable(tmp_path):
    dist = _make_dist(tmp_path)
    app = create_app(settings=make_settings(tmp_path, dist_dir=str(dist)))
    with TestClient(app) as client:
        response = client.get("/assets/app-abc.js")
        assert response.status_code == 200
        assert "immutable" in response.headers["cache-control"]
        assert response.text == "console.log('ok')"
    app.state.db.close()


def test_unknown_api_returns_json_404(tmp_path):
    dist = _make_dist(tmp_path)
    app = create_app(settings=make_settings(tmp_path, dist_dir=str(dist)))
    with TestClient(app) as client:
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"
    app.state.db.close()
