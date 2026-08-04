"""Debug endpoints — emotion introspection, token tracking, audit log, performance."""

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger("emoji-chat")


class LogLevelRequest(BaseModel):
    level: str  # DEBUG, INFO, WARNING, ERROR


class ClientLogRequest(BaseModel):
    level: str
    title: str = ""
    message: str = ""


@router.get("/api/debug/emotions")
def debug_emotions():
    """Return AI self-affect, drives, and user affect for the debug panel."""
    result = {
        "ai": {"emoji": "😶", "label": "未知", "values": {}},
        "drives": {},
        "user": {},
    }

    try:
        from services.emotion.self_affect import get_self_mood_display
        result["ai"] = get_self_mood_display()
    except Exception:
        pass

    try:
        from services.drive.engine import get_drive_values
        result["drives"] = get_drive_values()
    except Exception:
        pass

    try:
        from services.emotion.affect import get_affect
        result["user"] = get_affect()
    except Exception:
        pass

    return result


@router.get("/api/debug/token-requests")
def debug_token_requests():
    """Return list of recent request IDs for the token viewer dropdown."""
    try:
        from app.token_tracker import get_all_request_ids
        return {"requests": get_all_request_ids()}
    except Exception:
        return {"requests": []}


@router.get("/api/debug/tokens")
def debug_tokens(request_id: str = Query(..., min_length=1)):
    """Return token records for a specific request."""
    try:
        from app.token_tracker import get_token_records
        records = get_token_records(request_id)
        return {"records": records, "count": len(records)}
    except Exception:
        return {"records": [], "count": 0}


@router.get("/api/debug/drift")
def debug_drift():
    """Return current persona drift status for the debug panel."""
    try:
        from services.identity.drift_detector import get_drift_status
        return get_drift_status()
    except Exception:
        return {"available": False, "reason": "查询失败"}


# ── Relationship / psychology dashboard endpoints ────────────────────


@router.get("/api/debug/affinity")
def debug_affinity():
    """10D affinity values + full milestone checklist for the debug panel."""
    try:
        from services.emotion.affinity import init_affinity_db, get_affinity, get_milestones, _MILESTONES
        init_affinity_db()
        aff = get_affinity()
        achieved = {m["name"] for m in get_milestones()}
        milestones = [
            {
                "name": name, "description": desc, "dimension": dim,
                "threshold": threshold,
                "value": round(aff.get(dim, 0), 3),
                "reached": name in achieved,
            }
            for dim, threshold, name, desc in _MILESTONES
        ]
        return {"values": aff, "milestones": milestones}
    except Exception:
        return {"values": {}, "milestones": []}


@router.get("/api/debug/psych")
def debug_psych():
    """Aggregate attachment, contagion, goal, salience, curiosity for the debug panel."""
    result = {"attachment": None, "contagion": None, "goal": None,
              "salience": {}, "curiosity": []}
    try:
        import json as _json, os as _os
        from app.config import STYLE_PATH
        if _os.path.exists(STYLE_PATH):
            with open(STYLE_PATH) as f:
                result["attachment"] = _json.load(f)
    except Exception:
        pass
    try:
        from services.emotion.contagion import _load_state as _load_contagion
        result["contagion"] = _load_contagion()
    except Exception:
        pass
    try:
        from services.psych.conversation_goal import _load_state as _load_goal
        result["goal"] = _load_goal()
    except Exception:
        pass
    try:
        from services.emotion.salience import get_salience, init_salience_db
        init_salience_db()
        result["salience"] = get_salience()
    except Exception:
        pass
    try:
        from services.psych.entry_point import _load as _load_curiosity
        result["curiosity"] = _load_curiosity()
    except Exception:
        pass
    return result


@router.get("/api/debug/life-domains")
def debug_life_domains():
    """6 life domains with CN labels for the debug panel."""
    try:
        from services.psych.life_domains import _load, DOMAINS
        data = _load()
        domains = [
            {"key": key, "label": DOMAINS[key]["label"],
             "status": data.get(key, {}).get("status", "neutral"),
             "salience": data.get(key, {}).get("salience", 0.0),
             "last_mention": data.get(key, {}).get("last_mention", "")}
            for key in DOMAINS
        ]
        domains.sort(key=lambda d: d["salience"], reverse=True)
        return {"domains": domains}
    except Exception:
        return {"domains": []}


@router.get("/api/debug/portrait")
def debug_portrait():
    """Synthesized user portrait + key stats for the debug panel."""
    result = {"portrait": "", "stats": {"kg_entities": 0, "first_date": "",
                                         "total_messages": 0, "total_days": 0}}
    try:
        from services.psych.user_model import _get_raw_data, synthesize_portrait
        data = _get_raw_data()
        result["portrait"] = synthesize_portrait(data)
    except Exception:
        pass
    try:
        from app.db import q
        row = q("SELECT COUNT(*) AS c FROM kg_entities", fetch="one")
        if row:
            result["stats"]["kg_entities"] = row["c"]
    except Exception:
        pass
    try:
        import json as _json, os as _os
        from app.config import MEMORY_DIR
        from datetime import datetime as _dt, timezone as _tz
        p = _os.path.join(MEMORY_DIR, "timeline.json")
        if _os.path.exists(p):
            with open(p) as f:
                tl = _json.load(f)
            result["stats"]["first_date"] = tl.get("first_date", "")
            result["stats"]["total_messages"] = tl.get("total_lines", 0)
            if tl.get("first_date"):
                fd = _dt.fromisoformat(tl["first_date"]).date()
                result["stats"]["total_days"] = (_dt.now(_tz.utc).date() - fd).days + 1
    except Exception:
        pass
    return result


# ── Audit log endpoints ──────────────────────────────────────────────


@router.get("/api/debug/audit")
def debug_audit(
    category: str = Query(""),
    operation: str = Query(""),
    search: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    date_from: str = Query(""),
    date_to: str = Query(""),
):
    """Query audit log with optional filters and pagination."""
    from app.audit import query_audit
    return query_audit(category, operation, search, limit, offset, date_from, date_to)


@router.get("/api/debug/audit/categories")
def debug_audit_categories():
    """Return distinct (category, operation) pairs for filter dropdowns."""
    from app.audit import get_audit_categories
    return {"categories": get_audit_categories()}


@router.get("/api/debug/performance")
def debug_performance(
    since_hours: int = Query(24, ge=1, le=720),
    step_name: str = Query(""),
):
    """Return P50/P95/P99 latency percentiles from system_trace."""
    from app.audit import get_performance_stats
    return get_performance_stats(since_hours, step_name)


@router.post("/api/debug/loglevel")
def debug_set_log_level(body: LogLevelRequest):
    """Change the emoji-chat logger level at runtime."""
    from app.log_setup import set_log_level
    new_level = set_log_level(body.level)
    return {"ok": True, "level": new_level}


@router.post("/api/log/client")
def receive_client_log(body: ClientLogRequest):
    """Receive a log event from the browser for server-side persistence."""
    from app.audit import audit_log

    level = body.level.lower()
    log_level = {"error": logging.ERROR, "warn": logging.WARNING, "info": logging.INFO}.get(level, logging.INFO)
    logger.log(log_level, "[client] %s: %s", body.title, body.message)

    if level in ("error", "warn"):
        audit_log(
            operation="client_log",
            category="system",
            detail=f"{body.title}: {body.message[:200]}",
            metadata={"client_level": level},
        )
    return {"ok": True}


@router.get("/api/debug/token-history")
def debug_token_history(
    since_hours: int = Query(168, ge=1, le=2160),
    limit: int = Query(200, ge=1, le=1000),
):
    """Return persistent token records from the database."""
    from app.token_tracker import get_token_records_from_db
    return {"records": get_token_records_from_db(limit, since_hours)}
