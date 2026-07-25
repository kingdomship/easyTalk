"""Lightweight step tracer for debugging the chat pipeline.

Usage:
    from app.tracer import set_request_id, step

    set_request_id()  # at entry point (once per request)

    with step("build_context"):
        ctx = _build_context(msg)

    with step("llm_main", detail="reply generation"):
        reply = _call_llm(prompt)

Each trace is persisted to the system_trace table and also logged
at DEBUG level with format: [trace] rid | step | status | elapsed
"""

import contextvars
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Generator

from app.db import execute

logger = logging.getLogger("emoji-chat")

# ── Request ID — dual storage for cross-thread propagation ──────────
# threading.local() is per-thread; it does NOT propagate through
# asyncio.to_thread() or ThreadPoolExecutor. ContextVar DOES propagate
# through asyncio.to_thread(), so we store in both and prefer ContextVar.

import threading

_tls = threading.local()
_request_id_ctx = contextvars.ContextVar("request_id", default="")


def set_request_id(rid: str | None = None) -> str:
    """Set the current request ID. Call once at the entry point.

    Writes to both threading.local() (for direct thread access) and
    ContextVar (for cross-thread propagation via asyncio.to_thread).
    """
    rid = rid or uuid.uuid4().hex[:12]
    _tls.request_id = rid
    _request_id_ctx.set(rid)
    return rid


def get_request_id() -> str:
    """Get the current request ID. Prefers ContextVar (cross-thread safe)."""
    rid = _request_id_ctx.get("")
    if rid:
        return rid
    if not hasattr(_tls, "request_id") or not _tls.request_id:
        _tls.request_id = uuid.uuid4().hex[:12]
    return _tls.request_id


# ── Step tracer ──────────────────────────────────────────────────────


@contextmanager
def step(name: str, detail: str = "", user_agent: str = "", ip_address: str = "") -> Generator[None, None, None]:
    """Trace a single step: record start, status, elapsed, and error.

    Example:
        with step("llm_main", "reply generation"):
            reply = _call_llm(prompt)

    If the block raises, status="error" is recorded and the exception
    is re-raised. DB insert failures are silently swallowed so tracing
    never breaks the pipeline.
    """
    rid = get_request_id()
    t0 = time.perf_counter()
    status = "ok"
    error_msg = ""

    try:
        yield
    except Exception:
        status = "error"
        # Capture exception info without consuming the traceback
        exc_type, exc_value = None, None
        import sys
        exc_type, exc_value, _ = sys.exc_info()
        error_msg = f"{exc_type.__name__ if exc_type else '???'}: {str(exc_value)[:200]}"
        raise
    finally:
        elapsed = (time.perf_counter() - t0) * 1000  # ms
        logger.info(
            "[trace] %s | %-24s | %s | %7.1fms%s",
            rid,
            name,
            status,
            elapsed,
            f" | {detail}" if detail else "",
        )
        # Persist to DB (best-effort, never crash the pipeline)
        try:
            execute(
                "INSERT INTO system_trace (request_id, step_name, detail, "
                "elapsed_ms, status, error_msg, user_agent, ip_address) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [rid, name, detail, round(elapsed, 2), status, error_msg,
                 user_agent[:500] if user_agent else "",
                 ip_address[:45] if ip_address else ""],
            )
        except Exception:
            pass


def trace_event(event_type: str, **props: object) -> None:
    """Record a one-shot event to system_trace (not a span).

    For key events that don't fit the step() context-manager pattern.
    """
    rid = get_request_id()
    detail = ", ".join(f"{k}={v}" for k, v in props.items() if v)[:200]
    try:
        execute(
            "INSERT INTO system_trace (request_id, step_name, detail, "
            "elapsed_ms, status) VALUES (%s, %s, %s, %s, %s)",
            [rid, event_type, detail, 0, "ok"],
        )
    except Exception:
        pass
