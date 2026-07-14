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
    aff = get_affinity()
    from services.affinity import get_milestones
    aff["milestones"] = get_milestones()
    return aff


@router.get("/api/idle-thought")
def latest_idle_thought():
    """Return the most recent idle thought, if within the last hour."""
    _ensure_db()
    from services.consciousness_loop import get_latest_idle_thought
    thought = get_latest_idle_thought()
    return {"thought": thought}


@router.get("/api/missing-you")
def missing_you():
    """Check if user has been away for >24h. Returns accumulated idle thoughts."""
    _ensure_db()
    last = q(
        "SELECT user_msg, created_at FROM chat_history ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if not last:
        return {"away": False}

    row = q(
        "SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs FROM chat_history ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    secs = float(row["secs"]) if row and row["secs"] else 0
    hours = secs / 3600.0

    if hours < 12:
        return {"away": False, "hours": round(hours, 1)}

    # Fetch accumulated idle thoughts from during the absence
    thoughts = q(
        "SELECT content, created_at FROM idle_thoughts "
        "WHERE EXTRACT(EPOCH FROM (NOW() - created_at)) < %s "
        "ORDER BY id ASC",
        [secs],
    )
    thought_texts = [t["content"] for t in thoughts[:8]]

    return {
        "away": True,
        "hours": round(hours, 1),
        "thoughts": thought_texts,
        "last_msg": last["user_msg"][:60] if last else "",
    }


@router.get("/api/narrative/situations")
def list_situations():
    """Return all detected conversation situations."""
    from services.narrative import get_situations
    return get_situations()


@router.get("/api/narrative/episodes")
def list_episodes():
    """Return all distilled narrative episodes."""
    from services.narrative import get_episodes
    return get_episodes()


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
            if ord(ch) > 127 and 0x1F300 <= ord(ch) <= 0x1F9FF:
                mood_emoji = ch
                break
        result.append({
            "date": str(r["date"]),
            "chat_count": r["chat_count"],
            "mood_emoji": mood_emoji,
        })
    return result
