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

# ── LLM module context for token tracking ─────────────────────────
# Set by callers (chat.py, services/*) before LLM calls so that
# token_tracker knows which logical module made each API call.
_llm_module_ctx = contextvars.ContextVar("llm_module", default="")

from contextlib import contextmanager


@contextmanager
def llm_module_context(name: str):
    """Set the current LLM module name for token tracking.

    Usage:
        with llm_module_context("analyze_intent"):
            resp = client.chat.completions.create(...)
    """
    token = _llm_module_ctx.set(name)
    try:
        yield
    finally:
        _llm_module_ctx.reset(token)


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


_low_priority_executor: ThreadPoolExecutor | None = None


def get_low_priority_executor() -> ThreadPoolExecutor:
    """Dedicated executor for analysis / batch tasks that can be delayed.

    Kept separate from the main background executor so that core state
    updates (affect, affinity, indexing) are never starved by slow
    analysis tasks (crystallize, guard, narrative, deep_audit, etc.).
    """
    global _low_priority_executor
    if _low_priority_executor is None:
        _low_priority_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-lo")
    return _low_priority_executor

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
            resp = original_create(*args, **kwargs)
        else:
            acquired = _LLM_SEMAPHORE.acquire(timeout=_LLM_SEMAPHORE_TIMEOUT)
            if not acquired:
                raise RuntimeError(
                    f"LLM rate limiter: {_LLM_SEMAPHORE_TIMEOUT}s timeout — "
                    "too many concurrent API calls"
                )
            try:
                resp = original_create(*args, **kwargs)
            finally:
                _LLM_SEMAPHORE.release()

        # Record token usage (foreground + background, all calls)
        try:
            from app.token_tracker import record_tokens
            from app.tracer import get_request_id

            usage = getattr(resp, "usage", None)
            if usage:
                model = getattr(resp, "model", "") or kwargs.get("model", "")
                record_tokens(
                    request_id=get_request_id(),
                    step_name=_llm_module_ctx.get("") or "unknown",
                    model=model,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    total_tokens=getattr(usage, "total_tokens", 0) or 0,
                )
        except Exception:
            pass  # token tracking must never break the pipeline

        return resp

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
    _reset_visual_llm()


# ── Visual LLM client ─────────────────────────────────────────────

_visual_llm_client: OpenAI | None = None
_visual_config_hash: str | None = None


def _reset_visual_llm():
    """Reset the visual LLM singleton (called by reset_llm too)."""
    global _visual_llm_client, _visual_config_hash
    _visual_llm_client = None
    _visual_config_hash = None


def get_visual_llm() -> OpenAI | None:
    """Get or create the visual LLM client singleton.

    Same pattern as get_llm(): singleton + semaphore rate-limiting +
    token tracking. Returns None if no visual API key is configured.
    """
    global _visual_llm_client, _visual_config_hash
    config = load_llm_config()
    vis = config.visual
    fp = f"{vis.base_url}|{vis.model}|{vis.api_key[-8:] if vis.api_key else 'nokey'}"

    if _visual_llm_client is None or _visual_config_hash != fp:
        if not vis.api_key:
            logger.warning("No visual API key configured — visual analysis disabled")
            _visual_llm_client = None
            _visual_config_hash = None
            return None
        raw = OpenAI(
            api_key=vis.api_key,
            base_url=vis.base_url,
        )
        _visual_llm_client = _wrap_llm_client(raw)
        _visual_config_hash = fp
    return _visual_llm_client


def stitch_frames(frames: list[dict]) -> str | None:
    """Stitch up to 4 frames into a 2×2 grid (640×480), return base64 JPEG.

    Layout: top-left=t≈-10s, top-right=t≈-6s,
            bottom-left=t≈-3s, bottom-right=t=0 (latest).

    Returns None if all frames fail to decode.
    """
    from PIL import Image
    from io import BytesIO
    import base64 as b64

    cell_w, cell_h = 320, 240
    grid = Image.new("RGB", (cell_w * 2, cell_h * 2), (0, 0, 0))
    positions = [(0, 0), (cell_w, 0), (0, cell_h), (cell_w, cell_h)]

    any_ok = False
    for i, pos in enumerate(positions):
        if i >= len(frames):
            break
        try:
            data = b64.b64decode(frames[i].get("image_base64", ""))
            img = Image.open(BytesIO(data)).resize((cell_w, cell_h))
            grid.paste(img, pos)
            any_ok = True
        except Exception:
            logger.warning("Frame %d decode failed, using black placeholder", i)

    if not any_ok:
        return None

    buf = BytesIO()
    grid.save(buf, format="JPEG", quality=80)
    return b64.b64encode(buf.getvalue()).decode("ascii")


_VISUAL_SYSTEM_PROMPT = (
    "你是视觉分析助手。请仔细观察画面，只描述你确实看到的物体和场景，"
    "不要猜测或编造不存在的内容。如果画面全黑、过曝或无法辨认，"
    "请直接说'画面不可用'。"
)


def analyze_frames(query: str, stitched_b64: str) -> str:
    """Send the stitched grid image + user query to the visual LLM.

    Returns the model's text description, or "" on any failure.
    """
    client = get_visual_llm()
    if client is None:
        return ""

    try:
        with llm_module_context("visual_analyze"):
            resp = client.chat.completions.create(
                model=load_llm_config().visual.model,
                messages=[
                    {"role": "system", "content": _VISUAL_SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": (
                            "这张2×2网格图从左到右从上到下是从旧到新的时序画面。"
                            f"请观察并回答：{query}"
                        )},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{stitched_b64}"
                        }},
                    ]},
                ],
                temperature=0.3,
                max_tokens=500,
                timeout=8.0,
            )
        return resp.choices[0].message.content.strip() or ""
    except Exception:
        logger.warning("Visual LLM analysis failed", exc_info=True)
        return ""


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
