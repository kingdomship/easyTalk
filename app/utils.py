"""Shared utilities for easyTalk services."""

import json
import logging
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

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


def get_llm():
    """Get or create the shared DeepSeek client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
    return _llm_client


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
