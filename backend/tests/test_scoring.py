"""熟练度分数段、首次作答、阶段步进与自评锚点（表驱动）。"""
from __future__ import annotations

import pytest

from app import scoring


@pytest.mark.parametrize(
    "mastery,label,code,stage",
    [
        (0, "不认识", "vague", 1),
        (15, "不认识", "vague", 1),
        (22.4, "不认识", "vague", 1),
        (22.5, "模糊", "fuzzy", 2),
        (30, "模糊", "fuzzy", 2),
        (37.4, "模糊", "fuzzy", 2),
        (37.5, "认识", "known", 3),
        (45, "认识", "known", 3),
        (52.4, "认识", "known", 3),
        (52.5, "很熟", "mastered", 4),
        (60, "很熟", "mastered", 4),
        (95, "很熟", "mastered", 4),
    ],
)
def test_mastery_level_and_stage(mastery, label, code, stage):
    assert scoring.mastery_level(mastery) == (label, code)
    assert scoring.stage_of(mastery) == stage


@pytest.mark.parametrize("mark,anchor", [(1, 15.0), (2, 30.0), (3, 45.0), (4, 60.0), (0, None)])
def test_mark_anchor(mark, anchor):
    assert scoring.mark_anchor(mark) == anchor


@pytest.mark.parametrize(
    "correct,response_ms,mastery,mark",
    [
        (False, 1000, 15.0, 1),
        (True, 1200, 45.0, 3),
        (True, 3000, 45.0, 3),
        (True, 3001, 30.0, 2),
        (True, 8000, 30.0, 2),
    ],
)
def test_first_encounter_result(correct, response_ms, mastery, mark):
    assert scoring.first_encounter_result(correct, response_ms) == (mastery, mark)


def test_first_encounter_in_next_mastery():
    fast = scoring.next_mastery(0, 0, 0, 0.0, 0, is_correct=True, response_ms=1200, mode="en2cn")
    assert (fast.mastery, fast.user_mark) == (45.0, 3)
    slow = scoring.next_mastery(0, 0, 0, 0.0, 0, is_correct=True, response_ms=8000, mode="en2cn")
    assert (slow.mastery, slow.user_mark) == (30.0, 2)
    wrong = scoring.next_mastery(0, 0, 0, 0.0, 0, is_correct=False, response_ms=1200, mode="en2cn")
    assert (wrong.mastery, wrong.user_mark) == (15.0, 1)


@pytest.mark.parametrize("previous,expected", [(15, 30), (30, 45), (45, 60), (60, 75), (89, 100)])
def test_correct_moves_one_stage(previous, expected):
    snapshot = scoring.next_mastery(
        previous, 4, 4, 4.0, 3, is_correct=True, response_ms=1000, mode="en2cn"
    )
    assert snapshot.mastery == expected
    assert snapshot.user_mark == scoring.stage_of(expected)


@pytest.mark.parametrize("previous,expected", [(15, 0), (30, 15), (45, 30), (60, 45), (95, 80)])
def test_wrong_moves_one_stage_down(previous, expected):
    snapshot = scoring.next_mastery(
        previous, 4, 3, 4.0, 3, is_correct=False, response_ms=1000, mode="en2cn"
    )
    assert snapshot.mastery == expected


def test_single_answer_never_skips_two_stages():
    for previous in range(0, 101):
        current = float(previous)
        up = scoring.next_mastery(
            current, 3, 3, 3.0, 3, is_correct=True, response_ms=1000, mode="en2cn"
        )
        down = scoring.next_mastery(
            current, 3, 3, 3.0, 3, is_correct=False, response_ms=1000, mode="en2cn"
        )
        assert scoring.stage_of(up.mastery) - scoring.stage_of(current) <= 1
        assert scoring.stage_of(current) - scoring.stage_of(down.mastery) <= 1


def test_dont_know_forces_mark_one():
    snapshot = scoring.next_mastery(
        45.0, 5, 5, 5.0, 3, is_correct=False, response_ms=1000, mode="en2cn", forced_mark=1
    )
    assert snapshot.mastery == 30.0
    assert snapshot.user_mark == 1


@pytest.mark.parametrize(
    "mode,previous,expected",
    [("en2cn", 15.0, 60.0), ("en2cn", 80.0, 80.0), ("cn2en", 45.0, 95.0)],
)
def test_mastered_action(mode, previous, expected):
    snapshot = scoring.next_mastery(
        previous, 3, 2, 2.0, 2, is_correct=True, response_ms=1000, mode=mode, action="mastered"
    )
    assert snapshot.mastery == expected
    assert snapshot.user_mark == 4


@pytest.mark.parametrize("count,choice", [(0, 0), (1, 1), (2, 1), (3, 2), (5, 3), (10, 6)])
def test_mode_split_default_ratio(count, choice):
    assert scoring.mode_split(count) == choice


@pytest.mark.parametrize(
    "count,ratio,choice",
    [
        (10, 0.65, 7),  # 6.5 四舍五入
        (10, 0.75, 8),  # 7.5 四舍五入
        (3, 0.5, 2),  # 1.5 → 2
        (10, 0.0, 0),
        (10, 1.0, 10),
        (20, 0.4, 8),
    ],
)
def test_mode_split_custom_ratio(count, ratio, choice):
    assert scoring.mode_split(count, ratio) == choice


def test_eligibility_excludes_above_90():
    assert scoring.is_eligible(90) is True
    assert scoring.is_eligible(90.1) is False
