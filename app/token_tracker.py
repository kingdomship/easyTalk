"""Thread-safe token usage tracker for LLM calls.

Every LLM call through _wrap_llm_client() (see app/utils.py) is recorded here.
Records are kept in a bounded deque (fast in-memory lookup for the debug panel)
and batch-flushed to the token_usage table for persistence across restarts.
"""

import logging
import threading
import time
from collections import deque
from typing import TypedDict

from app.db import execute, q

logger = logging.getLogger("emoji-chat")


class TokenRecord(TypedDict):
    request_id: str
    step_name: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    timestamp: float


_MAX_RECORDS = 500
_records: deque[TokenRecord] = deque(maxlen=_MAX_RECORDS)
_lock = threading.Lock()

# Batch-flush state (protected by _flush_lock)
_pending_flush: list[TokenRecord] = []
_last_flush_time: float = time.time()
_flush_lock = threading.Lock()
_FLUSH_BATCH_SIZE = 20
_FLUSH_INTERVAL_S = 30


def record_tokens(
    request_id: str,
    step_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> None:
    """Append a token usage record from an LLM call."""
    rec: TokenRecord = {
        "request_id": request_id,
        "step_name": step_name,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "timestamp": time.time(),
    }
    with _lock:
        _records.append(rec)

    # Accumulate for batch flush
    with _flush_lock:
        _pending_flush.append(rec)
    _maybe_flush_to_db()


def _maybe_flush_to_db() -> None:
    """Flush pending records to token_usage table if thresholds are met.

    Must be called outside _flush_lock to avoid deadlocks with the executor.
    """
    # Fast check outside lock first
    if len(_pending_flush) < _FLUSH_BATCH_SIZE and \
       time.time() - _last_flush_time < _FLUSH_INTERVAL_S:
        return

    batch: list[TokenRecord] = []
    with _flush_lock:
        if len(_pending_flush) < _FLUSH_BATCH_SIZE and \
           time.time() - _last_flush_time < _FLUSH_INTERVAL_S:
            return
        batch = list(_pending_flush)
        _pending_flush.clear()
        _last_flush_time = time.time()

    if batch:
        _do_flush(batch)


def _do_flush(batch: list[TokenRecord]) -> None:
    """Batch-INSERT records into token_usage table. Best-effort."""
    try:
        # Build multi-row INSERT
        values = []
        params = []
        for r in batch:
            values.append("(%s, %s, %s, %s, %s, %s)")
            params.extend([
                r["request_id"],
                r["step_name"],
                r["model"],
                r["prompt_tokens"],
                r["completion_tokens"],
                r["total_tokens"],
            ])
        sql = "INSERT INTO token_usage (request_id, step_name, model, prompt_tokens, completion_tokens, total_tokens) VALUES " + ", ".join(values)
        execute(sql, params)
    except Exception:
        logger.exception("token batch flush failed (%d records)", len(batch))


def get_token_records(request_id: str) -> list[TokenRecord]:
    """Return all token records for a specific request, oldest first."""
    with _lock:
        return [r for r in _records if r["request_id"] == request_id]


def get_all_request_ids() -> list[dict]:
    """Return distinct request IDs with timestamp and count, most recent first."""
    with _lock:
        seen: dict[str, dict] = {}
        for r in _records:
            rid = r["request_id"]
            if rid not in seen:
                seen[rid] = {"id": rid, "timestamp": r["timestamp"], "count": 0}
            seen[rid]["count"] += 1
    # Also include records from DB (from before last restart)
    try:
        db_ids = q(
            "SELECT DISTINCT request_id, MIN(created_at) AS ts, COUNT(*) AS cnt "
            "FROM token_usage GROUP BY request_id ORDER BY ts DESC LIMIT 50",
            fetch="all",
        )
        for row in db_ids:
            rid = row["request_id"]
            if rid not in seen:
                seen[rid] = {
                    "id": rid,
                    "timestamp": row["ts"].timestamp(),
                    "count": row["cnt"],
                }
    except Exception:
        pass
    return sorted(seen.values(), key=lambda x: x["timestamp"], reverse=True)


def get_token_records_from_db(limit: int = 200, since_hours: int = 168) -> list[dict]:
    """Query persistent token records from the database."""
    try:
        rows = q(
            "SELECT request_id, step_name, model, prompt_tokens, completion_tokens, "
            "total_tokens, created_at FROM token_usage "
            "WHERE created_at >= NOW() - INTERVAL '%s hours' "
            "ORDER BY created_at DESC LIMIT %s",
            [since_hours, limit],
            fetch="all",
        )
        return [dict(r) for r in rows]
    except Exception:
        return []
