"""Audit trail for user operations.

Every user-initiated action is recorded to the audit_log table via a
background executor so it never blocks the event loop.

Usage:
    from app.audit import audit_log, query_audit, get_performance_stats
    audit_log("chat_message", "chat", detail="hello", metadata={"len": 5})
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.db import execute, q
from app.tracer import get_request_id

logger = logging.getLogger("emoji-chat")

_audit_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audit-")

_OPERATION_LABELS: dict[str, str] = {
    "chat_message": "聊天消息",
    "chat_stream": "流式聊天",
    "delete_emotion": "删除情绪",
    "list_diaries": "日记列表",
    "view_diary": "查看日记",
    "generate_diary": "生成AI日记",
    "generate_user_diary": "生成用户日记",
    "on_this_day": "去年今日",
    "save_config": "保存配置",
    "save_api_key": "保存API Key",
    "view_persona": "查看人设",
    "view_profile": "查看用户画像",
    "fetch_news": "抓取新闻",
    "analyze_visual": "视觉分析",
    "client_log": "前端日志",
}


def _write_audit(record: dict) -> None:
    """Execute DB INSERT in background thread. Silently swallows errors."""
    try:
        execute(
            "INSERT INTO audit_log (request_id, category, operation, detail, "
            "metadata, status_code, duration_ms, user_agent, ip_address) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                record["request_id"],
                record["category"],
                record["operation"],
                record["detail"],
                record.get("metadata", "{}"),
                record.get("status_code", 200),
                record.get("duration_ms", 0),
                record.get("user_agent", ""),
                record.get("ip_address", ""),
            ],
        )
    except Exception:
        logger.exception("audit write failed")


def audit_log(
    operation: str,
    category: str,
    detail: str = "",
    metadata: dict | None = None,
    duration_ms: float = 0,
    status_code: int = 200,
    user_agent: str = "",
    ip_address: str = "",
) -> None:
    """Record a user operation to the audit trail.

    This is fire-and-forget: the write is submitted to a background
    thread pool and the call returns immediately. Failures are logged
    to the container log but never raise.

    Args:
        operation: Action name (e.g. "chat_message", "save_config")
        category: Domain (e.g. "chat", "config", "diary")
        detail: Human-readable description (max 500 chars)
        metadata: Arbitrary JSON-serializable dict for filtering
        duration_ms: Request duration in milliseconds
        status_code: HTTP status code
        user_agent: Browser user-agent string
        ip_address: Client IP address
    """
    try:
        record = {
            "request_id": get_request_id(),
            "category": category,
            "operation": operation,
            "detail": detail[:500] if detail else "",
            "metadata": json_dumps_safe(metadata) if metadata else "{}",
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "user_agent": user_agent[:500],
            "ip_address": ip_address[:45],
        }
        _audit_executor.submit(_write_audit, record)
    except Exception:
        pass  # audit must never interrupt business logic


def query_audit(
    category: str = "",
    operation: str = "",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
    date_from: str = "",
    date_to: str = "",
) -> dict:
    """Query audit log with optional filters.

    Returns: {"records": [...], "total": int}
    """
    conditions = []
    params: list = []

    if category:
        conditions.append("category = %s")
        params.append(category)
    if operation:
        conditions.append("operation = %s")
        params.append(operation)
    if search:
        conditions.append("detail ILIKE %s")
        params.append(f"%{search}%")
    if date_from:
        conditions.append("created_at >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= %s")
        params.append(date_to)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    try:
        total_row = q(
            f"SELECT COUNT(*) AS cnt FROM audit_log {where}",
            params,
            fetch="one",
        )
        total = total_row["cnt"] if total_row else 0

        rows = q(
            f"SELECT id, request_id, category, operation, detail, metadata, "
            f"status_code, duration_ms, user_agent, ip_address, created_at "
            f"FROM audit_log {where} "
            f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
            fetch="all",
        )

        records = []
        for r in rows:
            label = _OPERATION_LABELS.get(r["operation"], r["operation"])
            records.append({
                "id": r["id"],
                "request_id": r["request_id"],
                "category": r["category"],
                "operation": r["operation"],
                "operation_label": label,
                "detail": r["detail"],
                "metadata": r["metadata"],
                "status_code": r["status_code"],
                "duration_ms": r["duration_ms"],
                "user_agent": r["user_agent"],
                "ip_address": r["ip_address"],
                "created_at": _format_dt(r["created_at"]),
            })

        return {"records": records, "total": total}
    except Exception:
        logger.exception("query_audit failed")
        return {"records": [], "total": 0}


def get_audit_categories() -> list[dict]:
    """Return distinct category+operation pairs for filter dropdowns."""
    try:
        rows = q(
            "SELECT DISTINCT category, operation FROM audit_log "
            "ORDER BY category, operation",
            fetch="all",
        )
        return [{"category": r["category"], "operation": r["operation"]} for r in rows]
    except Exception:
        return []


def get_performance_stats(since_hours: int = 24, step_name: str = "") -> dict:
    """Return P50/P95/P99 latency percentiles from system_trace.

    Args:
        since_hours: Look-back window in hours
        step_name: Optional filter for a specific step
    """
    conditions = ["created_at >= NOW() - INTERVAL '%s hours'"]
    params = [since_hours]

    if step_name:
        conditions.append("step_name = %s")
        params.append(step_name)

    where = "WHERE " + " AND ".join(conditions)

    # Use PERCENTILE_CONT for accurate percentiles
    try:
        rows = q(
            f"SELECT step_name, "
            f"PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY elapsed_ms) AS p50, "
            f"PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY elapsed_ms) AS p95, "
            f"PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY elapsed_ms) AS p99, "
            f"COUNT(*) AS cnt, AVG(elapsed_ms)::NUMERIC(8,1) AS avg_ms "
            f"FROM system_trace {where} "
            f"GROUP BY step_name ORDER BY avg_ms DESC",
            params,
            fetch="all",
        )
        return {
            "steps": [
                {
                    "step_name": r["step_name"],
                    "p50": round(float(r["p50"]), 1),
                    "p95": round(float(r["p95"]), 1),
                    "p99": round(float(r["p99"]), 1),
                    "count": r["cnt"],
                    "avg_ms": float(r["avg_ms"]),
                }
                for r in rows
            ],
            "since_hours": since_hours,
        }
    except Exception:
        logger.exception("get_performance_stats failed")
        return {"steps": [], "since_hours": since_hours}


# ── helpers ──────────────────────────────────────────────────────────


def json_dumps_safe(obj: object) -> str:
    """json.dumps with fallback, never raises."""
    import json as _json

    return _json.dumps(obj, ensure_ascii=False, default=str)


def _format_dt(val) -> str:
    """Format a datetime-like value to ISO string."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)
