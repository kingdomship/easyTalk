"""Diary endpoints."""

from datetime import date, timedelta
from fastapi import APIRouter
from app.db import q, init_db
from services.reflection.diary import generate_diary, generate_user_diary, get_diaries, get_diary

router = APIRouter()


@router.get("/api/diary")
def list_diaries(limit: int = 30, offset: int = 0, search: str = "",
                 date_from: str = "", date_to: str = ""):
    init_db()
    return get_diaries(limit=limit, offset=offset,
                       search=search, date_from=date_from, date_to=date_to)


@router.get("/api/diary/{for_date}")
def show_diary(for_date: str):
    init_db()
    entry = get_diary(for_date)
    if not entry:
        return {"error": "not found"}
    return entry


@router.post("/api/diary/generate")
def trigger_diary_gen(for_date: str = ""):
    init_db()
    if not for_date:
        for_date = (date.today() - timedelta(days=1)).isoformat()
    generate_diary(for_date)
    generate_user_diary(for_date)
    return {"ok": True, "date": for_date}


@router.post("/api/diary/generate-user")
def trigger_user_diary_gen(for_date: str = ""):
    init_db()
    if not for_date:
        for_date = (date.today() - timedelta(days=1)).isoformat()
    result = generate_user_diary(for_date)
    return {"ok": True, "date": for_date, "has_user_diary": result is not None}


@router.get("/api/diary/on-this-day")
def on_this_day():
    init_db()
    today = date.today()
    return q(
        "SELECT * FROM diary_entries WHERE EXTRACT(MONTH FROM date) = %s AND EXTRACT(DAY FROM date) = %s AND date < %s ORDER BY date DESC",
        [today.month, today.day, today.isoformat()],
    )
