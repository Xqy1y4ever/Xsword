"""循环练习、循环设置与今日概览接口。"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import cycle
from ..config import Settings
from ..deps import auth, get_conn, get_settings
from ..schemas import CycleAdjustIn, CycleAnswerIn, CycleSettingsIn

router = APIRouter(prefix="/api", tags=["cycle"])


def _http_error(exc: cycle.CycleError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"error": exc.code, "message": exc.message})


@router.get("/settings")
def read_settings(conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    return cycle.get_settings(conn)


@router.put("/settings")
def write_settings(
    payload: CycleSettingsIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    try:
        with conn:
            return cycle.update_settings(conn, payload.cycleSize, payload.choiceRatio)
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc


@router.get("/today")
def today(
    conn: sqlite3.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
    _: dict = Depends(auth),
):
    return cycle.today_snapshot(conn, settings.timezone)


@router.post("/cycle/start")
def start_cycle(
    conn: sqlite3.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
    _: dict = Depends(auth),
):
    with conn:
        result = cycle.start_cycle(conn, settings.timezone)
    if result["cycle"] is None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "no_eligible_words",
                "message": "没有可练的单词了（熟练度高于 90 的词不再出现，词库也可能为空）",
            },
        )
    return result


@router.get("/cycle/current")
def current_cycle(conn: sqlite3.Connection = Depends(get_conn), _: dict = Depends(auth)):
    return {"cycle": cycle.active_cycle(conn)}


@router.get("/cycle/{cycle_id}/next")
def next_question(
    cycle_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    try:
        return cycle.next_question(conn, cycle_id)
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc


@router.post("/cycle/{cycle_id}/answer")
def answer_question(
    cycle_id: int,
    payload: CycleAnswerIn,
    conn: sqlite3.Connection = Depends(get_conn),
    settings: Settings = Depends(get_settings),
    _: dict = Depends(auth),
):
    try:
        with conn:
            return cycle.answer(conn, cycle_id, payload.model_dump(), settings.timezone)
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc


@router.post("/cycle/{cycle_id}/adjust")
def adjust_question(
    cycle_id: int,
    payload: CycleAdjustIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    try:
        with conn:
            return cycle.adjust_answer(conn, cycle_id, payload.model_dump())
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc


@router.post("/cycle/{cycle_id}/abandon")
def abandon_cycle(
    cycle_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    try:
        with conn:
            cycle.abandon_cycle(conn, cycle_id)
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc
    return {"ok": True}


@router.get("/cycle/{cycle_id}/review-cards")
def review_cards(
    cycle_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    try:
        return {"cards": cycle.review_cards(conn, cycle_id)}
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc


@router.post("/cycle/{cycle_id}/cards/{word_id}/read")
def mark_card_read(
    cycle_id: int,
    word_id: int,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict = Depends(auth),
):
    try:
        with conn:
            return cycle.mark_card_read(conn, cycle_id, word_id)
    except cycle.CycleError as exc:
        raise _http_error(exc) from exc
