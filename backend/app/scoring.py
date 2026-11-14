"""熟练度、分数段与答题结算。

分数与自评（选义四档）：不认识 15 / 模糊 30 / 认识 45 / 很熟 60。
分数段（用于显示与判定阶段）：
- 0–22.5   不认识
- 22.5–37.5 模糊
- 37.5–52.5 认识
- > 52.5   很熟
- > 90     视为已掌握，不再进入循环

首次见到一个单词（seen=0）：
- 答错 / 点「不会」   → 15（不认识档）
- 3 秒内答对          → 45（认识档）
- 3 秒外答对          → 30（模糊档）

之后的答题：答对 +15、答错 -15（每次最多只跨一个阶段，因为阶段边界间距就是 15）。
「已熟练」：选义 → 60（很熟档）；拼写 → 95（退出循环）。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

FAST_MS = {"en2cn": 3000, "cn2en": 6000}
FIRST_CORRECT_FAST_MS = 3000

MARK_LABELS = {0: "未标记", 1: "不认识", 2: "模糊", 3: "认识", 4: "很熟"}
MARK_ANCHORS = {1: 15.0, 2: 30.0, 3: 45.0, 4: 60.0}

# 阶段边界（相邻间距 15，保证单次 ±15 不会跨两个阶段）
STAGE_BOUNDS = (22.5, 37.5, 52.5)
MASTERY_LEVELS = (
    (STAGE_BOUNDS[0], "不认识", "vague"),
    (STAGE_BOUNDS[1], "模糊", "fuzzy"),
    (STAGE_BOUNDS[2], "认识", "known"),
    (101, "很熟", "mastered"),
)

FIRST_WRONG_SCORE = 15.0
FIRST_FAST_SCORE = 45.0
FIRST_SLOW_SCORE = 30.0
CORRECT_STEP = 15.0
WRONG_STEP = 15.0

MASTERED_CHOICE_SCORE = 60.0
MASTERED_SPELLING_SCORE = 95.0
CARD_READ_GAIN = 10.0

MODE_CHOICE_RATIO = 0.6  # 每轮目标：60% 题目为选义
MASTERY_EXCLUDE = 90.0
REVIEW_CARD_MAX = 30.0  # 循环结束后回顾 ≤30 分的卡片

# 题型门槛：熟练度 > 50 才可能出拼写；> 60 不再出释义（50–60 两种都可能）
CHOICE_MAX_MASTERY = 60.0
SPELLING_MIN_MASTERY = 50.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mastery_level(mastery: float) -> tuple[str, str]:
    for upper, label, code in MASTERY_LEVELS:
        if mastery < upper:
            return label, code
    return "很熟", "mastered"


def stage_of(mastery: float) -> int:
    """1 不认识 / 2 模糊 / 3 认识 / 4 很熟。"""
    return {"vague": 1, "fuzzy": 2, "known": 3, "mastered": 4}[mastery_level(mastery)[1]]


def mark_anchor(user_mark: int) -> float | None:
    return MARK_ANCHORS.get(int(user_mark))


def is_eligible(mastery: float) -> bool:
    return mastery <= MASTERY_EXCLUDE


def can_choice(mastery: float) -> bool:
    """释义题门槛：熟练度 ≤ 60。"""
    return mastery <= CHOICE_MAX_MASTERY


def can_spell(mastery: float) -> bool:
    """拼写题门槛：熟练度 > 50。"""
    return mastery > SPELLING_MIN_MASTERY


def first_encounter_result(is_correct: bool, response_ms: int) -> tuple[float, int]:
    if not is_correct:
        return FIRST_WRONG_SCORE, 1
    if response_ms <= FIRST_CORRECT_FAST_MS:
        return FIRST_FAST_SCORE, stage_of(FIRST_FAST_SCORE)
    return FIRST_SLOW_SCORE, stage_of(FIRST_SLOW_SCORE)


def mastered_target(mode: str) -> float:
    return MASTERED_CHOICE_SCORE if mode == "en2cn" else MASTERED_SPELLING_SCORE


def mode_split(count: int, ratio: float | None = None) -> int:
    """按比例返回 count 道题里「选义」的数量（四舍五入），其余为拼写。"""
    if count <= 0:
        return 0
    value = MODE_CHOICE_RATIO if ratio is None else clamp(float(ratio), 0.0, 1.0)
    choice = int(math.floor(count * value + 0.5))
    return max(0, min(count, choice))


def speed_score(response_ms: int, mode: str) -> float:
    fast = FAST_MS.get(mode, 5000)
    if response_ms <= fast:
        return 1.0
    if response_ms <= fast * 2:
        return 0.75
    return 0.5


@dataclass
class ProgressSnapshot:
    seen: int
    correct: int
    wrong: int
    speed_score_sum: float
    user_mark: int
    mastery: float


def next_mastery(
    previous_mastery: float,
    seen: int,
    correct: int,
    speed_score_sum: float,
    user_mark: int,
    *,
    is_correct: bool,
    response_ms: int,
    mode: str,
    action: str = "submit",
    forced_mark: int | None = None,
) -> ProgressSnapshot:
    """一次作答后的进度快照（含熟练度与自评）。"""
    seen2 = seen + 1
    correct2 = correct + (1 if is_correct else 0)
    speed2 = speed_score_sum + (speed_score(response_ms, mode) if is_correct else 0.5)

    if action == "mastered":
        target = mastered_target(mode)
        mastery = max(previous_mastery, target)
        mark = 4
    elif seen == 0:
        mastery, mark = first_encounter_result(is_correct, response_ms)
    elif is_correct:
        mastery = clamp(previous_mastery + CORRECT_STEP, 0.0, 100.0)
        mark = stage_of(mastery)
    else:
        mastery = clamp(previous_mastery - WRONG_STEP, 0.0, 100.0)
        mark = stage_of(mastery)

    if forced_mark is not None:
        mark = forced_mark
    return ProgressSnapshot(
        seen=seen2,
        correct=correct2,
        wrong=seen2 - correct2,
        speed_score_sum=speed2,
        user_mark=mark,
        mastery=round(clamp(mastery, 0.0, 100.0), 1),
    )
