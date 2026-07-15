"""Memory, affinity, and mood endpoints."""

from fastapi import APIRouter
from app.db import q, init_db
from services.emotion.affinity import init_affinity_db, get_affinity

router = APIRouter()


@router.get("/api/memory/persona")
def get_persona():
    from services.memory.loader import get_persona as _get_persona
    return {"content": _get_persona()}


@router.get("/api/memory/profile")
def get_user_profile():
    from services.memory.loader import get_user_profile as _get_profile
    return {"content": _get_profile()}


@router.get("/api/affinity")
def show_affinity():
    init_db()
    init_affinity_db()
    aff = get_affinity()
    from services.emotion.affinity import get_milestones
    aff["milestones"] = get_milestones()
    return aff


@router.get("/api/idle-thought")
def latest_idle_thought():
    """Return the most recent idle thought, if within the last hour."""
    init_db()
    from services.reflection.consciousness_loop import get_latest_idle_thought
    thought = get_latest_idle_thought()
    return {"thought": thought}


@router.get("/api/missing-you")
def missing_you():
    """Check if user has been away for >24h. Returns accumulated idle thoughts."""
    init_db()
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


@router.get("/api/constellation")
def constellation():
    """Return memory constellation data for the star map visualization."""
    init_db()
    from services.memory.clustering import build_constellation
    return build_constellation()


@router.get("/api/narrative/situations")
def list_situations():
    """Return all detected conversation situations."""
    from services.memory.narrative import get_situations
    return get_situations()


@router.get("/api/narrative/episodes")
def list_episodes():
    """Return all distilled narrative episodes."""
    from services.memory.narrative import get_episodes
    return get_episodes()


@router.get("/api/mood/calendar")
def mood_calendar(days: int = 60):
    init_db()
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


@router.get("/api/kg/entities")
def kg_entities(limit: int = 50):
    """List all known entities ordered by last_seen."""
    init_db()
    return q(
        "SELECT id, name, type, first_seen, last_seen, metadata "
        "FROM kg_entities ORDER BY last_seen DESC LIMIT %s",
        [limit],
    )


@router.get("/api/kg/relationships")
def kg_relationships(limit: int = 50):
    """List current active relationships."""
    init_db()
    return q(
        "SELECT r.id, e_src.name AS source, e_tgt.name AS target, "
        "r.relation, r.strength, r.valid_at, r.invalid_at "
        "FROM kg_relationships r "
        "JOIN kg_entities e_src ON e_src.id = r.source_id "
        "JOIN kg_entities e_tgt ON e_tgt.id = r.target_id "
        "ORDER BY r.valid_at DESC LIMIT %s",
        [limit],
    )
