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

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Generator

from app.db import execute

logger = logging.getLogger("emoji-chat")

# ── Thread-local request ID ──────────────────────────────────────────

import threading

_tls = threading.local()


def set_request_id(rid: str | None = None) -> str:
    """Set the current request ID. Call once at the entry point.

    Args:
        rid: Optional request ID. If None, a 12-char hex UUID is generated.
    Returns:
        The request ID that was set.
    """
    _tls.request_id = rid or uuid.uuid4().hex[:12]
    return _tls.request_id


def get_request_id() -> str:
    """Get the current request ID. Auto-generates one if not set."""
    if not hasattr(_tls, "request_id") or not _tls.request_id:
        _tls.request_id = uuid.uuid4().hex[:12]
    return _tls.request_id


# ── Step tracer ──────────────────────────────────────────────────────


@contextmanager
def step(name: str, detail: str = "") -> Generator[None, None, None]:
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
        import sys
        exc_type, exc_value, _ = sys.exc_info()
        error_msg = f"{exc_type.__name__}: {str(exc_value)[:200]}"
        raise
    finally:
        elapsed = (time.perf_counter() - t0) * 1000  # ms
        logger.debug(
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
                "elapsed_ms, status, error_msg) VALUES (%s, %s, %s, %s, %s, %s)",
                [rid, name, detail, round(elapsed, 2), status, error_msg],
            )
        except Exception:
            pass
