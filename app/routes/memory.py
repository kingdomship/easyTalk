"""Memory, affinity, and mood endpoints."""

from fastapi import APIRouter
from app.db import q
from app.routes.chat import _ensure_db
from services.affinity import init_affinity_db, get_affinity

router = APIRouter()


@router.get("/api/memory/persona")
def get_persona():
    from services.memory_loader import get_persona as _get_persona
    return {"content": _get_persona()}


@router.get("/api/memory/profile")
def get_user_profile():
    from services.memory_loader import get_user_profile as _get_profile
    return {"content": _get_profile()}


@router.get("/api/affinity")
def show_affinity():
    _ensure_db()
    init_affinity_db()
    return get_affinity()


@router.get("/api/mood/calendar")
def mood_calendar(days: int = 60):
    _ensure_db()
    rows = q(
        "SELECT date, chat_count, content FROM diary_entries ORDER BY date DESC LIMIT %s",
        [days],
    )
    result = []
    for r in rows:
        mood_emoji = "✨"
        for ch in (r.get("content") or ""):
            if ord(ch) > 127 and any(0x1F300 <= ord(ch) <= 0x1F9FF):
                mood_emoji = ch
                break
        result.append({
            "date": str(r["date"]),
            "chat_count": r["chat_count"],
            "mood_emoji": mood_emoji,
        })
    return result
