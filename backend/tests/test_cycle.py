"""循环制练习：60/40 题型分配、低熟练度优先、首次/后续评分、回顾卡片。"""
from __future__ import annotations

from app import util

from tests.conftest import add_word


def _set_progress(app, word_id, *, mastery=0.0, seen=0, correct=0, speed=0.0, mark=0):
    conn = app.state.db.conn()
    with conn:
        conn.execute(
            """INSERT INTO progress(word_id, seen, correct, wrong, speed_score_sum, user_mark, mastery,
                                    streak, first_seen_date, updated_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT(word_id) DO UPDATE SET
                 seen = excluded.seen, correct = excluded.correct, wrong = excluded.wrong,
                 speed_score_sum = excluded.speed_score_sum, user_mark = excluded.user_mark,
                 mastery = excluded.mastery""",
            (word_id, seen, correct, seen - correct, speed, mark, mastery, util.today_str(), util.now_iso()),
        )


def _make_cycle(app, entries, *, finished=False):
    """直接造一个循环，便于固定题型做精确断言。entries: [(word_id, mode)]"""
    conn = app.state.db.conn()
    stamp = util.now_iso()
    with conn:
        cursor = conn.execute(
            """INSERT INTO cycles(date, started_at, size, answered, correct, finished_at)
               VALUES(?, ?, ?, 0, 0, ?)""",
            (util.today_str(), stamp, len(entries), stamp if finished else None),
        )
        cycle_id = int(cursor.lastrowid)
        for pos, (word_id, mode) in enumerate(entries):
            conn.execute(
                """INSERT INTO cycle_items(cycle_id, word_id, pos, mode, mastery_at_start)
                   VALUES(?, ?, ?, ?, 0)""",
                (cycle_id, word_id, pos, mode),
            )
    return cycle_id


def _start(client):
    return client.post("/api/cycle/start")


def _next(client, cycle_id):
    return client.get(f"/api/cycle/{cycle_id}/next").json()


def _answer(client, cycle_id, word_id, *, action="submit", answer="", response_ms=900):
    return client.post(
        f"/api/cycle/{cycle_id}/answer",
        json={"wordId": word_id, "action": action, "answer": answer, "responseMs": response_ms},
    ).json()


def _correct_answer(client, question):
    word = client.get(f"/api/words/{question['wordId']}").json()
    return word["meaning"] if question["mode"] == "en2cn" else word["term"]


def test_cycle_settings(auth_client):
    assert auth_client.get("/api/settings").json() == {"cycleSize": 20, "choiceRatio": 0.6}
    assert auth_client.put("/api/settings", json={"cycleSize": 5}).json() == {
        "cycleSize": 5,
        "choiceRatio": 0.6,
    }
    assert auth_client.put(
        "/api/settings", json={"cycleSize": 5, "choiceRatio": 0.65}
    ).json() == {"cycleSize": 5, "choiceRatio": 0.65}
    assert auth_client.put("/api/settings", json={"cycleSize": 0}).status_code == 400
    assert auth_client.put("/api/settings", json={"cycleSize": 500}).status_code == 400
    assert (
        auth_client.put("/api/settings", json={"cycleSize": 5, "choiceRatio": 1.5}).status_code
        == 400
    )


def _mixed_pool(auth_client, app, count=10):
    """一半词只能选义（20 分），一半词只能拼写（70 分）。"""
    for index in range(count):
        low = add_word(auth_client, f"ratioLow{index}", f"低于{index}")
        _set_progress(app, low["id"], mastery=20.0, seen=2, correct=1, speed=2.0, mark=1)
        high = add_word(auth_client, f"ratioHigh{index}", f"高于{index}")
        _set_progress(app, high["id"], mastery=70.0, seen=6, correct=5, speed=5.0, mark=4)


def test_cycle_mode_ratio_custom(auth_client, app):
    _mixed_pool(auth_client, app, count=10)
    auth_client.put("/api/settings", json={"cycleSize": 10, "choiceRatio": 0.8})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert len(items) == 10
    assert len([1 for _, mode, _ in items if mode == "en2cn"]) == 8
    assert len([1 for _, mode, _ in items if mode == "cn2en"]) == 2


def test_cycle_mode_ratio_rounds_half_up(auth_client, app):
    _mixed_pool(auth_client, app, count=10)
    auth_client.put("/api/settings", json={"cycleSize": 10, "choiceRatio": 0.65})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert len([1 for _, mode, _ in items if mode == "en2cn"]) == 7  # 6.5 → 7
    assert len([1 for _, mode, _ in items if mode == "cn2en"]) == 3


def test_cycle_ratio_zero_is_all_spelling(auth_client, app):
    for index in range(10):
        word = add_word(auth_client, f"spellOnly{index}", f"拼写{index}")
        _set_progress(app, word["id"], mastery=70.0, seen=6, correct=5, speed=5.0, mark=4)
    auth_client.put("/api/settings", json={"cycleSize": 10, "choiceRatio": 0.0})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert items and all(mode == "cn2en" for _, mode, _ in items)


def test_start_cycle_respects_size_and_unique_words(auth_client):
    for index in range(8):
        add_word(auth_client, f"word{index}", f"释义{index}")
    auth_client.put("/api/settings", json={"cycleSize": 4})
    cycle = _start(auth_client).json()["cycle"]
    assert cycle["size"] == 4

    seen = []
    for _ in range(4):
        question = _next(auth_client, cycle["id"])["question"]
        seen.append(question["wordId"])
        _answer(auth_client, cycle["id"], question["wordId"], action="dont_know")
    assert len(set(seen)) == 4
    assert _next(auth_client, cycle["id"])["finished"] is True


def _modes_of(app, cycle_id):
    conn = app.state.db.conn()
    return [
        (int(row["word_id"]), row["mode"], float(row["mastery_at_start"]))
        for row in conn.execute(
            "SELECT word_id, mode, mastery_at_start FROM cycle_items WHERE cycle_id = ? ORDER BY pos",
            (cycle_id,),
        ).fetchall()
    ]


def test_mode_split_respects_mastery_thresholds(auth_client, app):
    # 10 个低分词（≤50：只能释义）+ 10 个高分词（>60：只能拼写）
    for index in range(10):
        low = add_word(auth_client, f"low{index}", f"低分{index}")
        _set_progress(app, low["id"], mastery=20.0, seen=2, correct=1, speed=2.0, mark=1)
        high = add_word(auth_client, f"high{index}", f"高分{index}")
        _set_progress(app, high["id"], mastery=70.0, seen=6, correct=5, speed=5.0, mark=4)
    auth_client.put("/api/settings", json={"cycleSize": 10})
    cycle = _start(auth_client).json()["cycle"]

    items = _modes_of(app, cycle["id"])
    assert len(items) == 10
    choices = [item for item in items if item[1] == "en2cn"]
    spells = [item for item in items if item[1] == "cn2en"]
    assert len(choices) == 6
    assert len(spells) == 4
    assert all(mastery <= 60 for _, _, mastery in choices)  # >60 不出释义
    assert all(mastery > 50 for _, _, mastery in spells)  # ≤50 不出拼写


def test_mastery_above_60_never_gets_choice_questions(auth_client, app):
    for index in range(10):
        word = add_word(auth_client, f"spell{index}", f"拼写{index}")
        _set_progress(app, word["id"], mastery=70.0, seen=6, correct=5, speed=5.0, mark=4)
    auth_client.put("/api/settings", json={"cycleSize": 10})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert items
    assert all(mode == "cn2en" for _, mode, _ in items)


def test_mastery_below_50_never_gets_spelling_questions(auth_client, app):
    for index in range(10):
        word = add_word(auth_client, f"choice{index}", f"选义{index}")
        _set_progress(app, word["id"], mastery=20.0, seen=2, correct=1, speed=2.0, mark=1)
    auth_client.put("/api/settings", json={"cycleSize": 10})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert items
    assert all(mode == "en2cn" for _, mode, _ in items)


def test_overlap_band_50_to_60_can_get_both(auth_client, app):
    for index in range(10):
        word = add_word(auth_client, f"mid{index}", f"中间{index}")
        _set_progress(app, word["id"], mastery=55.0, seen=4, correct=3, speed=3.0, mark=3)
    auth_client.put("/api/settings", json={"cycleSize": 10})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert len([1 for _, mode, _ in items if mode == "en2cn"]) == 6
    assert len([1 for _, mode, _ in items if mode == "cn2en"]) == 4


def test_all_unseen_words_only_choice(auth_client, app):
    # 全新词熟练度 0（≤50），按门槛不能出拼写，只能全出释义
    for index in range(10):
        add_word(auth_client, f"fresh{index}", f"新词{index}")
    auth_client.put("/api/settings", json={"cycleSize": 10})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert len(items) == 10
    assert all(mode == "en2cn" for _, mode, _ in items)


def test_mode_split_small_cycle(auth_client, app):
    for index in range(3):
        word = add_word(auth_client, f"smalllow{index}", f"低{index}")
        _set_progress(app, word["id"], mastery=20.0, seen=2, correct=1, speed=2.0, mark=1)
    for index in range(2):
        word = add_word(auth_client, f"smallhigh{index}", f"高{index}")
        _set_progress(app, word["id"], mastery=70.0, seen=6, correct=5, speed=5.0, mark=4)
    auth_client.put("/api/settings", json={"cycleSize": 5})
    cycle = _start(auth_client).json()["cycle"]
    items = _modes_of(app, cycle["id"])
    assert len([1 for _, mode, _ in items if mode == "en2cn"]) == 3
    assert len([1 for _, mode, _ in items if mode == "cn2en"]) == 2


def test_low_mastery_words_are_selected_first(auth_client, app):
    words = []
    for index, mastery in enumerate((10.0, 20.0, 30.0, 40.0, 50.0)):
        word = add_word(auth_client, f"weak{index}", f"释义{index}")
        _set_progress(app, word["id"], mastery=mastery, seen=3, correct=3, speed=3.0, mark=2)
        words.append((word, mastery))
    auth_client.put("/api/settings", json={"cycleSize": 3})
    cycle = _start(auth_client).json()["cycle"]

    conn = app.state.db.conn()
    selected = [
        int(row["word_id"])
        for row in conn.execute(
            "SELECT word_id FROM cycle_items WHERE cycle_id = ? ORDER BY pos", (cycle["id"],)
        ).fetchall()
    ]
    assert selected == [words[0][0]["id"], words[1][0]["id"], words[2][0]["id"]]

    first = _next(auth_client, cycle["id"])["question"]
    assert first["wordId"] == words[0][0]["id"]


def test_start_cycle_resumes_active(auth_client):
    add_word(auth_client, "resume", "恢复")
    first = _start(auth_client).json()
    second = _start(auth_client).json()
    assert second["resumed"] is True
    assert second["cycle"]["id"] == first["cycle"]["id"]


def test_words_above_90_are_excluded(auth_client, app):
    normal = add_word(auth_client, "normal", "普通词")
    mastered = add_word(auth_client, "mastered", "已掌握")
    _set_progress(app, mastered["id"], mastery=95.0, seen=10, correct=10, speed=10.0, mark=4)
    auth_client.put("/api/settings", json={"cycleSize": 10})
    cycle = _start(auth_client).json()["cycle"]
    assert cycle["size"] == 1
    assert _next(auth_client, cycle["id"])["question"]["wordId"] == normal["id"]
    assert auth_client.get("/api/today").json()["eligibleCount"] == 1


def test_start_cycle_without_eligible_words(auth_client, app):
    word = add_word(auth_client, "done", "已完成")
    _set_progress(app, word["id"], mastery=99.0, seen=10, correct=10, speed=10.0, mark=4)
    response = _start(auth_client)
    assert response.status_code == 409
    assert response.json()["error"] == "no_eligible_words"


def test_first_encounter_fast_correct_45(auth_client, app):
    word = add_word(auth_client, "swift", "迅速的")
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    result = _answer(auth_client, cycle_id, word["id"], answer=word["meaning"], response_ms=1200)
    assert result["correct"] is True
    assert result["masteryAfter"] == 45.0
    assert result["userMark"] == 3


def test_first_encounter_slow_correct_30(auth_client, app):
    word = add_word(auth_client, "slowpoke", "慢性子")
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    result = _answer(auth_client, cycle_id, word["id"], answer=word["meaning"], response_ms=8000)
    assert result["masteryAfter"] == 30.0
    assert result["userMark"] == 2


def test_question_and_memory_include_pos(auth_client, app):
    word = add_word(auth_client, "vivid", "生动的", pos="adj.")
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    question = _next(auth_client, cycle_id)["question"]
    assert question["wordPos"] == "adj."
    result = _answer(auth_client, cycle_id, word["id"], answer="错误答案")
    assert result["pos"] == "adj."
    card = auth_client.get(f"/api/words/{word['id']}/annotation").json()
    assert card["pos"] == "adj."


def test_first_encounter_wrong_15(auth_client, app):
    word = add_word(auth_client, "novice", "新手")
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    result = _answer(auth_client, cycle_id, word["id"], answer="错误答案")
    assert result["correct"] is False
    assert result["masteryAfter"] == 15.0
    assert result["userMark"] == 1


def test_second_answer_correct_adds_one_stage(auth_client, app):
    word = add_word(auth_client, "steady", "稳定的")
    _set_progress(app, word["id"], mastery=30.0, seen=5, correct=4, speed=4.0, mark=2)
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    result = _answer(auth_client, cycle_id, word["id"], answer=word["meaning"], response_ms=500)
    assert result["masteryAfter"] == 45.0
    assert result["userMark"] == 3


def test_second_answer_wrong_drops_one_stage(auth_client, app):
    word = add_word(auth_client, "fragile", "脆弱的")
    _set_progress(app, word["id"], mastery=45.0, seen=5, correct=4, speed=4.0, mark=3)
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    result = _answer(auth_client, cycle_id, word["id"], answer="错误答案", response_ms=500)
    assert result["masteryAfter"] == 30.0
    assert result["userMark"] == 2


def test_mastered_choice_sets_60(auth_client, app):
    word = add_word(auth_client, "literacy", "读写能力")
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    result = _answer(auth_client, cycle_id, word["id"], action="mastered")
    assert result["masteryAfter"] == 60.0
    assert result["userMark"] == 4
    assert result["showMemory"] is False


def test_mastered_spelling_sets_95(auth_client, app):
    word = add_word(auth_client, "literacy", "读写能力")
    _set_progress(app, word["id"], mastery=60.0, seen=5, correct=4, speed=4.0, mark=4)
    cycle_id = _make_cycle(app, [(word["id"], "cn2en")])
    result = _answer(auth_client, cycle_id, word["id"], action="mastered")
    assert result["masteryAfter"] == 95.0
    assert result["userMark"] == 4
    assert auth_client.get("/api/today").json()["eligibleCount"] == 0


def test_review_cards_after_cycle_and_read_gain(auth_client, app):
    low = add_word(auth_client, "fuzzy", "模糊的")
    high = add_word(auth_client, "solid", "扎实的")
    _set_progress(app, low["id"], mastery=15.0, seen=5, correct=3, speed=3.0, mark=1)
    _set_progress(app, high["id"], mastery=60.0, seen=5, correct=4, speed=4.0, mark=4)
    cycle_id = _make_cycle(app, [(low["id"], "en2cn"), (high["id"], "en2cn")])

    assert auth_client.get(f"/api/cycle/{cycle_id}/review-cards").status_code == 409

    _answer(auth_client, cycle_id, low["id"], answer="错误答案")
    _answer(auth_client, cycle_id, high["id"], answer=high["meaning"])
    assert _next(auth_client, cycle_id)["finished"] is True

    cards = auth_client.get(f"/api/cycle/{cycle_id}/review-cards").json()["cards"]
    assert len(cards) == 1
    assert cards[0]["term"] == "fuzzy"
    assert cards[0]["mastery"] == 0.0
    assert cards[0]["cardRead"] is False
    assert cards[0]["memory"]["term"] == "fuzzy"

    read = auth_client.post(f"/api/cycle/{cycle_id}/cards/{low['id']}/read").json()
    assert read["gained"] == 10.0
    assert read["mastery"] == 10.0
    assert read["cardRead"] is True

    again = auth_client.post(f"/api/cycle/{cycle_id}/cards/{low['id']}/read").json()
    assert again["gained"] == 0.0
    assert again["mastery"] == 10.0


def test_review_card_requires_answered_item(auth_client, app):
    word = add_word(auth_client, "unknown", "未知的")
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    _answer(auth_client, cycle_id, word["id"], answer="错误答案")
    other = add_word(auth_client, "other", "其他")
    response = auth_client.post(f"/api/cycle/{cycle_id}/cards/{other['id']}/read")
    assert response.status_code == 404


def test_abandon_cycle(auth_client):
    add_word(auth_client, "abandon", "放弃")
    cycle = _start(auth_client).json()["cycle"]
    assert auth_client.post(f"/api/cycle/{cycle['id']}/abandon").status_code == 200
    assert auth_client.get("/api/cycle/current").json()["cycle"] is None


def test_cycle_answer_validation(auth_client, app):
    first = add_word(auth_client, "validate", "验证")
    second = add_word(auth_client, "other", "其他")
    cycle_id = _make_cycle(app, [(first["id"], "en2cn"), (second["id"], "en2cn")])
    outsider = add_word(auth_client, "outsider", "局外")
    response = auth_client.post(
        f"/api/cycle/{cycle_id}/answer",
        json={"wordId": outsider["id"], "answer": "x", "responseMs": 500},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "word_not_in_cycle"

    _answer(auth_client, cycle_id, first["id"], answer="错误答案")
    duplicate = auth_client.post(
        f"/api/cycle/{cycle_id}/answer",
        json={"wordId": first["id"], "answer": "x", "responseMs": 500},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"] == "already_answered"

    _answer(auth_client, cycle_id, second["id"], answer="错误答案")
    assert _next(auth_client, cycle_id)["finished"] is True
    finished = auth_client.post(
        f"/api/cycle/{cycle_id}/answer",
        json={"wordId": second["id"], "answer": "x", "responseMs": 500},
    )
    assert finished.status_code == 409
    assert finished.json()["error"] == "cycle_finished"


def test_today_snapshot_fields(auth_client):
    add_word(auth_client, "snapshot", "快照")
    body = auth_client.get("/api/today").json()
    assert body["settings"]["cycleSize"] == 20
    assert body["activeCycle"] is None
    assert body["today"]["cycles"] == 0
    assert body["totalWords"] == 1
    assert body["eligibleCount"] == 1
    assert set(body["mastery"]).issuperset({"不认识", "模糊", "认识", "很熟"})


def test_spelling_answer_can_rollback_or_mark_mastered(auth_client, app):
    word = add_word(auth_client, "resilient", "有韧性的")
    _set_progress(app, word["id"], mastery=60.0, seen=6, correct=5, speed=5.0, mark=4)
    cycle_id = _make_cycle(app, [(word["id"], "cn2en")])

    result = _answer(auth_client, cycle_id, word["id"], answer=word["term"])
    assert result["correct"] is True
    assert result["masteryAfter"] == 75.0

    # 模糊：回滚到答题前的 60
    fuzzy = auth_client.post(
        f"/api/cycle/{cycle_id}/adjust", json={"wordId": word["id"], "choice": "fuzzy"}
    ).json()
    assert fuzzy["masteryAfter"] == 60.0
    assert fuzzy["choice"] == "fuzzy"
    assert auth_client.get(f"/api/words/{word['id']}").json()["mastery"] == 60.0

    # 已熟练：提到 95（>90），不再进入循环
    mastered = auth_client.post(
        f"/api/cycle/{cycle_id}/adjust", json={"wordId": word["id"], "choice": "mastered"}
    ).json()
    assert mastered["masteryAfter"] == 95.0
    assert mastered["eligible"] is False
    assert auth_client.get(f"/api/words/{word['id']}").json()["mastery"] == 95.0


def test_spelling_adjust_wrong_answer_rolls_back_too(auth_client, app):
    word = add_word(auth_client, "brittle", "易碎的")
    _set_progress(app, word["id"], mastery=45.0, seen=5, correct=4, speed=4.0, mark=3)
    cycle_id = _make_cycle(app, [(word["id"], "cn2en")])
    result = _answer(auth_client, cycle_id, word["id"], answer="wrong")
    assert result["correct"] is False
    assert result["masteryAfter"] == 30.0

    fuzzy = auth_client.post(
        f"/api/cycle/{cycle_id}/adjust", json={"wordId": word["id"], "choice": "fuzzy"}
    ).json()
    assert fuzzy["masteryAfter"] == 45.0


def test_adjust_rejects_choice_question_and_unanswered(auth_client, app):
    word = add_word(auth_client, "soothe", "安抚")
    _set_progress(app, word["id"], mastery=30.0, seen=4, correct=3, speed=3.0, mark=2)
    cycle_id = _make_cycle(app, [(word["id"], "en2cn")])
    early = auth_client.post(
        f"/api/cycle/{cycle_id}/adjust", json={"wordId": word["id"], "choice": "fuzzy"}
    )
    assert early.status_code == 409
    assert early.json()["error"] == "not_answered"

    _answer(auth_client, cycle_id, word["id"], answer=word["meaning"])
    wrong_mode = auth_client.post(
        f"/api/cycle/{cycle_id}/adjust", json={"wordId": word["id"], "choice": "fuzzy"}
    )
    assert wrong_mode.status_code == 400
    assert wrong_mode.json()["error"] == "only_spelling"


def test_positions_are_shuffled_within_same_mastery(auth_client, app):
    """同熟练度的词不能按 id（=词表字母序）成串出现。"""
    ids = []
    for index in range(15):
        word = add_word(auth_client, f"same{index}", f"同分{index}")
        ids.append(word["id"])
    auth_client.put("/api/settings", json={"cycleSize": 15})
    cycle = _start(auth_client).json()["cycle"]
    conn = app.state.db.conn()
    order = [
        int(row["word_id"])
        for row in conn.execute(
            "SELECT word_id FROM cycle_items WHERE cycle_id = ? ORDER BY pos", (cycle["id"],)
        ).fetchall()
    ]
    assert sorted(order) == sorted(ids)
    assert order != sorted(ids)  # 同分随机，几乎不可能刚好等于 id 升序


def test_stats_include_cycles(auth_client):
    word = add_word(auth_client, "stats", "统计")
    auth_client.put("/api/settings", json={"cycleSize": 1})
    cycle = _start(auth_client).json()["cycle"]
    question = _next(auth_client, cycle["id"])["question"]
    _answer(auth_client, cycle["id"], question["wordId"], answer=_correct_answer(auth_client, question))
    stats = auth_client.get("/api/stats").json()
    assert stats["totals"]["cycles"] == 1
    assert stats["totals"]["cyclesToday"] == 1
    assert stats["today"]["cycles"] == 1
    assert stats["weakWords"][0]["term"] == "stats"


def test_word_cannot_appear_three_cycles_in_a_row(auth_client, app):
    word = add_word(auth_client, "repeat", "重复")
    spare = add_word(auth_client, "spare", "备用")
    _set_progress(app, spare["id"], mastery=95.0, seen=10, correct=10, speed=10.0, mark=4)
    # 最近两个循环里都有这个词 → 本轮不能再选
    _make_cycle(app, [(word["id"], "en2cn")], finished=True)
    _make_cycle(app, [(word["id"], "en2cn")], finished=True)
    response = _start(auth_client)
    assert response.status_code == 409
    assert response.json()["error"] == "no_eligible_words"


def test_word_allowed_again_after_missing_one_cycle(auth_client, app):
    word = add_word(auth_client, "repeat", "重复")
    spare = add_word(auth_client, "spare", "备用")
    _set_progress(app, spare["id"], mastery=95.0, seen=10, correct=10, speed=10.0, mark=4)
    _make_cycle(app, [(word["id"], "en2cn")], finished=True)
    _make_cycle(app, [(word["id"], "en2cn")], finished=True)
    # 第三个循环里没出现 → 连续记录被打断，下一轮可以再选
    _make_cycle(app, [(spare["id"], "en2cn")], finished=True)
    cycle = _start(auth_client).json()["cycle"]
    assert cycle["size"] == 1
    assert _next(auth_client, cycle["id"])["question"]["wordId"] == word["id"]


def test_word_allowed_if_only_appeared_in_last_cycle(auth_client, app):
    word = add_word(auth_client, "fresh", "新词")
    _make_cycle(app, [(word["id"], "en2cn")], finished=True)
    cycle = _start(auth_client).json()["cycle"]
    assert cycle["size"] == 1
    assert _next(auth_client, cycle["id"])["question"]["wordId"] == word["id"]
