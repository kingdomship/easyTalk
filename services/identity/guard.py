"""Identity immune system — prevent AI persona drift.

Now delegates to drift_detector (Mahalanobis-distance + multi-level classification)
instead of LLM-based subjective scoring. The periodic guard loads recent replies
and runs them through the mathematical drift detector.

Runs every 30 turns in a background thread.
"""

import json
import logging
import os
import threading

logger = logging.getLogger("emoji-chat")

from app.config import ARCHIVE_PATH

_CHECK_EVERY = 30
_guard_lock = threading.Lock()
_last_check_count = 0


def _load_recent_replies(n: int = 5) -> list[str]:
    """Load the last N AI replies from conversation archive."""
    replies = []
    try:
        if os.path.exists(ARCHIVE_PATH):
            from collections import deque
            with open(ARCHIVE_PATH) as f:
                last_lines = list(deque(f, maxlen=n * 6))
            for line in reversed(last_lines):
                try:
                    rec = json.loads(line)
                    assistant = rec.get("assistant", "")
                    if assistant:
                        replies.append(assistant)
                        if len(replies) >= n:
                            break
                except Exception:
                    logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return list(reversed(replies))


def maybe_guard():
    """Check for persona drift every _CHECK_EVERY turns.

    Simplified: delegates to drift_detector.check_and_intervene() for each
    recent reply. The Mahalanobis-distance approach is zero-API-cost and
    provides multi-level classification with trend prediction.
    """
    global _last_check_count
    if not _guard_lock.acquire(blocking=False):
        return
    try:
        if not os.path.exists(ARCHIVE_PATH):
            return
        with open(ARCHIVE_PATH) as f:
            line_count = sum(1 for _ in f)
        if line_count - _last_check_count < _CHECK_EVERY:
            return
        _last_check_count = line_count

        from services.identity.drift_detector import check_and_intervene
        replies = _load_recent_replies(5)
        for reply in replies:
            check_and_intervene(reply)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    finally:
        _guard_lock.release()


def get_drift_correction() -> str:
    """Return correction prompt from drift_detector's most recent assessment.

    Called during _build_context() to inject intervention into system prompt.
    """
    from services.identity.drift_detector import get_drift_correction as dd_get_correction
    return dd_get_correction()
