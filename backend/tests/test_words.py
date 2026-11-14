"""词库 CRUD、导入导出、自评标记。"""
from __future__ import annotations

from tests.conftest import add_word


def test_create_and_get_word(auth_client):
    created = add_word(auth_client, "glamorous", "迷人的", phonetic="/ˈɡlæmərəs/", pos="adj.", tags="class-note")
    assert created["term"] == "glamorous"
    assert created["annotationStatus"] == "missing"
    detail = auth_client.get(f"/api/words/{created['id']}").json()
    assert detail["meaning"] == "迷人的"
    assert detail["phonetic"] == "/ˈɡlæmərəs/"
    assert detail["pos"] == "adj."


def test_pos_can_be_patched_and_exported(auth_client):
    word = add_word(auth_client, "harbor", "港口", pos="n., v.")
    patched = auth_client.patch(f"/api/words/{word['id']}", json={"pos": "n., v., adj."})
    assert patched.status_code == 200
    assert patched.json()["pos"] == "n., v., adj."
    exported = auth_client.get("/api/words/export", params={"format": "json"}).json()
    assert exported["words"][0]["pos"] == "n., v., adj."


def test_duplicate_term_conflict(auth_client):
    add_word(auth_client, "rubric", "评分标准")
    response = auth_client.post("/api/words", json={"term": "Rubric", "meaning": "评分规则"})
    assert response.status_code == 409
    assert response.json()["error"] == "duplicate_term"


def test_list_search_sort_pagination(auth_client):
    for index in range(6):
        add_word(auth_client, f"word{index}", f"释义{index}")
    page = auth_client.get("/api/words", params={"page": 1, "pageSize": 4}).json()
    assert page["total"] == 6
    assert len(page["items"]) == 4
    page2 = auth_client.get("/api/words", params={"page": 2, "pageSize": 4}).json()
    assert len(page2["items"]) == 2
    search = auth_client.get("/api/words", params={"q": "word3"}).json()
    assert search["total"] == 1
    assert search["items"][0]["term"] == "word3"


def test_patch_and_delete(auth_client):
    word = add_word(auth_client, "detain", "拘留")
    patched = auth_client.patch(f"/api/words/{word['id']}", json={"meaning": "扣押；拘留"}).json()
    assert patched["meaning"] == "扣押；拘留"
    assert auth_client.delete(f"/api/words/{word['id']}").status_code == 200
    assert auth_client.get(f"/api/words/{word['id']}").status_code == 404


def test_import_text_parsing(auth_client):
    text = (
        "# 注释行\n"
        "mislead\t使误解\n"
        "sustain=维持\n"
        "vague:模糊的\n"
        "abundant,大量的\n"
        "\n"
        "这行没有分隔符\n"
        "sustain\t重复词\n"
    )
    result = auth_client.post("/api/words/import", json={"text": text}).json()
    assert result["added"] == 4
    reasons = [item["reason"] for item in result["skipped"]]
    assert "无法解析（需要 单词 + 分隔符 + 释义）" in reasons
    assert "已存在" in reasons


def test_export_json_and_csv(auth_client):
    add_word(auth_client, "cement", "巩固")
    payload = auth_client.get("/api/words/export", params={"format": "json"}).json()
    assert payload["words"][0]["term"] == "cement"
    csv_response = auth_client.get("/api/words/export", params={"format": "csv"})
    assert csv_response.status_code == 200
    assert "attachment" in csv_response.headers["content-disposition"]
    assert "cement" in csv_response.text


def test_mark_updates_mastery(auth_client, app):
    word = add_word(auth_client, "veto", "否决")
    low = auth_client.put(f"/api/words/{word['id']}/mark", json={"mark": 1}).json()
    high = auth_client.put(f"/api/words/{word['id']}/mark", json={"mark": 4}).json()
    assert high["mastery"] > low["mastery"]
    assert auth_client.get("/api/words").json()["items"][0]["userMark"] == 4


def test_purge_requires_confirmation(auth_client):
    add_word(auth_client, "verify", "核实")
    assert auth_client.post("/api/words/purge", json={"confirm": "no"}).status_code == 400
    assert auth_client.post("/api/words/purge", json={"confirm": "DELETE"}).status_code == 200
    assert auth_client.get("/api/words").json()["total"] == 0
