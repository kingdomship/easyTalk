"""Shared utilities for easyTalk services."""

import contextvars
import json
import logging
import os
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from app.llm_config import load_llm_config, LLMConfig

logger = logging.getLogger("emoji-chat")

_background_executor: ThreadPoolExecutor | None = None

# ── LLM rate limiter ──────────────────────────────────────────────
# Caps background LLM calls at N concurrent. Foreground calls (main
# chat reply + sprite generation) bypass the semaphore via a
# contextvar that propagates through asyncio.to_thread().

_LLM_SEMAPHORE = threading.Semaphore(4)
_LLM_SEMAPHORE_TIMEOUT = 60

# contextvars propagate to child threads (unlike threading.local),
# so asyncio.to_thread() carries the foreground flag automatically.
_llm_fg = contextvars.ContextVar("llm_fg", default=False)


def llm_foreground():
    """Mark the current async context as foreground — LLM calls bypass rate limit.

    Usage in chat.py:
        token = llm_foreground()
        resp = await asyncio.to_thread(_call_llm, client, msgs)
        llm_foreground_clear(token)
    """
    return _llm_fg.set(True)


def llm_foreground_clear(token: contextvars.Token) -> None:
    """Reset the foreground flag."""
    _llm_fg.reset(token)


def get_background_executor() -> ThreadPoolExecutor:
    """Return a shared ThreadPoolExecutor for background tasks.

    Replaces raw threading.Thread() with managed pool to prevent
    unbounded thread creation under load.
    """
    global _background_executor
    if _background_executor is None:
        _background_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="bg")
    return _background_executor

_llm_client = None
_current_config_hash: str | None = None


def _config_fingerprint(config: LLMConfig) -> str:
    """Stable fingerprint of LLM config for singleton invalidation."""
    return f"{config.base_url}|{config.model}|{config.api_key[-8:]}"


def get_llm_model() -> str:
    """Return the configured model name for use in LLM calls."""
    return load_llm_config().model


def _wrap_llm_client(client: OpenAI) -> OpenAI:
    """Wrap OpenAI client so all chat.completions.create calls are rate-limited.

    Uses a shared semaphore to cap concurrent API calls. Callers that cannot
    acquire a slot within _LLM_SEMAPHORE_TIMEOUT get a RuntimeError.
    """
    original_create = client.chat.completions.create

    def rate_limited_create(*args, **kwargs):
        # Foreground calls (main reply + sprite gen) bypass the semaphore.
        # Background tasks (self_evaluate, maybe_deep_audit, etc.) are capped.
        if _llm_fg.get():
            return original_create(*args, **kwargs)
        acquired = _LLM_SEMAPHORE.acquire(timeout=_LLM_SEMAPHORE_TIMEOUT)
        if not acquired:
            raise RuntimeError(
                f"LLM rate limiter: {_LLM_SEMAPHORE_TIMEOUT}s timeout — "
                "too many concurrent API calls"
            )
        try:
            return original_create(*args, **kwargs)
        finally:
            _LLM_SEMAPHORE.release()

    client.chat.completions.create = rate_limited_create  # type: ignore[method-assign]
    return client


def get_llm():
    """Get or create the shared OpenAI-compatible client singleton.

    Returns None if no API key is configured.
    Automatically rebuilds the client when config changes.
    All chat.completions.create calls through this client are rate-limited
    to _LLM_SEMAPHORE (5) concurrent calls.
    """
    global _llm_client, _current_config_hash
    config = load_llm_config()
    fp = _config_fingerprint(config)

    if _llm_client is None or _current_config_hash != fp:
        if not config.api_key:
            logger.warning("No API key configured — LLM calls will be skipped")
            _llm_client = None
            _current_config_hash = None
            return None
        raw = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
        _llm_client = _wrap_llm_client(raw)
        _current_config_hash = fp
    return _llm_client


def reset_llm():
    """Reset the LLM client so the next call re-reads config."""
    global _llm_client, _current_config_hash
    _llm_client = None
    _current_config_hash = None


def read_api_key() -> str | None:
    """Resolve API key from config. Returns None if not set."""
    return load_llm_config().api_key or None


def extract_json(raw: str) -> dict | None:
    """Extract the first JSON object from a raw LLM response using brace matching."""
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            return None
    return None


def read_last_n_lines(path: str, n: int) -> list[str]:
    """Read last N lines of a file efficiently using deque (no full-file load)."""
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return list(deque(f, maxlen=n))
    except Exception:
        logger.warning("read_last_n_lines failed: %s", path, exc_info=True)
        return []


def count_lines(path: str) -> int:
    """Count lines in a file with buffered iteration."""
    if not os.path.exists(path):
        return 0
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except Exception:
        logger.warning("count_lines failed: %s", path, exc_info=True)
        return 0
