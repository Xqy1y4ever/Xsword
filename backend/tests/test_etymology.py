"""词根库、词缀库、词族与记忆卡片。"""
from __future__ import annotations

from tests.conftest import add_word


def _import_annotation(client, payload: dict):
    return client.post("/api/annotate/import", json={"items": [payload]})


def test_annotation_creates_roots_and_family(auth_client):
    pharm = add_word(auth_client, "pharmacy", "药房")
    pharma = add_word(auth_client, "pharmaceutical", "制药的；药物")
    add_word(auth_client, "remedy", "疗法")

    assert _import_annotation(
        auth_client,
        {
            "word": "pharmacy",
            "breakdown": [{"form": "pharm", "type": "root", "key": "pharm", "gloss": "药", "origin": "Greek"}],
            "mnemonic": "pharm（药）+ -acy（场所）→ 卖药的地方",
        },
    ).status_code == 200
    assert _import_annotation(
        auth_client,
        {
            "word": "pharmaceutical",
            "breakdown": [
                {"form": "pharm", "type": "root", "key": "pharm", "gloss": "药", "origin": "Greek"},
                {"form": "ceutical", "type": "suffix", "key": "ceutical", "gloss": "制备"},
            ],
            "mnemonic": "pharm（药）+ ceutical（制备）→ 制药的",
            "cognates": ["pharmacy"],
        },
    ).status_code == 200

    roots = auth_client.get("/api/roots").json()
    assert roots["total"] == 1
    root = roots["items"][0]
    assert root["key"] == "pharm"
    assert root["words"] == 2

    detail = auth_client.get(f"/api/roots/{root['id']}").json()
    assert {item["term"] for item in detail["words"]} == {"pharmacy", "pharmaceutical"}

    card = auth_client.get(f"/api/words/{pharma['id']}/annotation").json()
    assert card["mnemonic"].startswith("pharm")
    assert card["roots"][0]["key"] == "pharm"
    assert card["cognates"][0]["term"] == "pharmacy"
    assert card["cognates"][0]["wordId"] == pharm["id"]
    assert {item["term"] for item in card["sameRootWords"]} == {"pharmacy"}

    affixes = auth_client.get("/api/affixes", params={"type": "suffix"}).json()["items"]
    assert affixes[0]["key"] == "ceutical"
    assert affixes[0]["words"] == 1


def test_annotation_is_idempotent(auth_client, app):
    word = add_word(auth_client, "insomnia", "失眠")
    payload = {
        "word": "insomnia",
        "breakdown": [{"form": "somn", "type": "root", "key": "somn", "gloss": "睡眠", "origin": "Latin"}],
        "mnemonic": "in-（不）+ somn（睡）→ 睡不着",
    }
    for _ in range(2):
        _import_annotation(auth_client, payload)
    conn = app.state.db.conn()
    assert conn.execute("SELECT COUNT(*) AS n FROM roots").fetchone()["n"] == 1
    assert conn.execute("SELECT COUNT(*) AS n FROM word_roots").fetchone()["n"] == 1
    assert auth_client.get(f"/api/words/{word['id']}/annotation").json()["status"] == "ok"


def test_import_annotation_for_unknown_word(auth_client):
    result = auth_client.post(
        "/api/annotate/import",
        json={"items": [{"word": "nonexistent", "breakdown": [], "mnemonic": "x"}]},
    ).json()
    assert result["ok"] == 0
    assert result["skipped"] == 1
    assert "词库中不存在" in result["errors"][0]


def test_annotate_status(auth_client):
    add_word(auth_client, "vague", "模糊的")
    status = auth_client.get("/api/annotate/status").json()
    assert status["total"] == 1
    assert status["missing"] == 1
