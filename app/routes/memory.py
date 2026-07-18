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
def mood_calendar(days: int = 60, date_from: str = "", date_to: str = ""):
    init_db()
    if date_from or date_to:
        where = []
        params = []
        if date_from:
            where.append("date >= %s")
            params.append(date_from)
        if date_to:
            where.append("date <= %s")
            params.append(date_to)
        clause = "WHERE " + " AND ".join(where)
        rows = q(
            f"SELECT date, chat_count, mood_emoji, content FROM diary_entries {clause} ORDER BY date DESC",
            params,
        )
    else:
        rows = q(
            "SELECT date, chat_count, mood_emoji, content FROM diary_entries ORDER BY date DESC LIMIT %s",
            [days],
        )
    result = []
    for r in rows:
        result.append({
            "date": str(r["date"]),
            "chat_count": r["chat_count"],
            "mood_emoji": r.get("mood_emoji") or "✨",
            "has_diary": bool(r.get("content")),
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


@router.get("/api/mood/affect-history")
def mood_affect_history(days: int = 7):
    """Return daily Panksepp 6-dimension averages for the last N days.

    Reads from affect_history table; if no data, falls back to current affect_state.
    """
    init_db()
    rows = q(
        "SELECT date, seeking, play, care, fear, rage, panic "
        "FROM affect_history "
        "WHERE date >= CURRENT_DATE - INTERVAL '%s days' "
        "ORDER BY date ASC",
        [days],
    )
    if rows:
        return rows
    # Fallback: return today's current affect as single data point
    from services.emotion.affect import get_affect
    aff = get_affect()
    today = __import__("datetime").date.today().isoformat()
    return [{
        "date": today,
        "seeking": aff.get("seeking", 0.35),
        "play": aff.get("play", 0.25),
        "care": aff.get("care", 0.2),
        "fear": aff.get("fear", 0.1),
        "rage": aff.get("rage", 0.05),
        "panic": aff.get("panic", 0.1),
    }]


@router.get("/api/mood/timeline")
def mood_timeline(days: int = 7):
    """Return daily emotion distribution for the last N days.

    Returns [{date, emotion_label, count}] grouped by date + emotion_label,
    plus daily totals for chart rendering.
    """
    init_db()
    rows = q(
        "SELECT DATE(created_at) AS date, emotion_label, COUNT(*) AS cnt "
        "FROM chat_history "
        "WHERE created_at >= NOW() - INTERVAL '%s days' "
        "GROUP BY DATE(created_at), emotion_label "
        "ORDER BY date DESC",
        [days],
    )
    # Build a per-date summary: {date: {label: count, total: N}}
    by_date = {}
    for r in (rows or []):
        d = str(r["date"])
        if d not in by_date:
            by_date[d] = {"total": 0, "labels": {}}
        by_date[d]["total"] += int(r["cnt"])
        by_date[d]["labels"][r["emotion_label"]] = int(r["cnt"])

    # Compute dominant emotion per day
    timeline = []
    for d in sorted(by_date.keys(), reverse=True):
        entry = by_date[d]
        labels = entry["labels"]
        dominant = max(labels, key=labels.get) if labels else ""
        timeline.append({
            "date": d,
            "total": entry["total"],
            "dominant": dominant,
            "labels": labels,
        })
    return timeline
