"""Shared utilities for easyTalk services."""

import json
import logging
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from app.llm_config import load_llm_config, LLMConfig

logger = logging.getLogger("emoji-chat")

_background_executor: ThreadPoolExecutor | None = None


def get_background_executor() -> ThreadPoolExecutor:
    """Return a shared ThreadPoolExecutor for background tasks.

    Replaces raw threading.Thread() with managed pool to prevent
    unbounded thread creation under load.
    """
    global _background_executor
    if _background_executor is None:
        _background_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg")
    return _background_executor

_llm_client = None
_current_config_hash: str | None = None


def _config_fingerprint(config: LLMConfig) -> str:
    """Stable fingerprint of LLM config for singleton invalidation."""
    return f"{config.base_url}|{config.model}|{config.api_key[-8:]}"


def get_llm_model() -> str:
    """Return the configured model name for use in LLM calls."""
    return load_llm_config().model


def get_llm():
    """Get or create the shared OpenAI-compatible client singleton.

    Returns None if no API key is configured.
    Automatically rebuilds the client when config changes.
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
        _llm_client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
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
