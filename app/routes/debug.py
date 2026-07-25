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
