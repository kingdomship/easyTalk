"""Periodic data lifecycle management — cleanup with semantic preservation.

Runs daily at 3:07 AM. Old chat data is pruned after sufficient time
for the four-layer memory system (condense → crystallize → narrate → profile)
to have extracted and preserved all meaningful patterns.
"""

import logging
import os
import json
from datetime import datetime, timedelta, timezone

from app.db import q, execute
from app.config import ARCHIVE_PATH

logger = logging.getLogger("emoji-chat")


def cleanup_old_data():
    """Main entry — scheduled daily at 3:07 AM."""
    try:
        _cleanup_chat_history(retention_days=90)
        _cleanup_idle_thoughts(retention_days=30)
        _cleanup_mood_history(retention_days=30)
        _cleanup_conversation_archive(max_lines=500, keep_lines=250)
        logger.info("Data lifecycle cleanup completed")
    except Exception:
        logger.warning("Data cleanup failed", exc_info=True)


def _cleanup_chat_history(retention_days: int):
    """Delete old chat_history rows and their memory_vectors.

    Old chats have already been compressed into summaries (every 50 turns),
    distilled into crystals (repeated topics), and woven into narrative
    episodes. The raw rows are safe to delete.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    deleted_mv = execute(
        "DELETE FROM memory_vectors WHERE chat_id IN "
        "(SELECT id FROM chat_history WHERE created_at < %s)",
        [cutoff],
    )
    deleted_ch = execute(
        "DELETE FROM chat_history WHERE created_at < %s",
        [cutoff],
    )
    if deleted_ch:
        logger.info("Cleaned %d old chat rows (retention=%d days)", deleted_ch, retention_days)


def _cleanup_idle_thoughts(retention_days: int):
    """Delete old idle thoughts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    deleted = execute("DELETE FROM idle_thoughts WHERE created_at < %s", [cutoff])
    if deleted:
        logger.info("Cleaned %d old idle thoughts", deleted)


def _cleanup_mood_history(retention_days: int):
    """Delete old mood history entries."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    deleted = execute("DELETE FROM mood_history WHERE created_at < %s", [cutoff])
    if deleted:
        logger.info("Cleaned %d old mood entries", deleted)


def _cleanup_conversation_archive(max_lines: int, keep_lines: int):
    """Truncate the conversation archive JSONL file.

    Old archive content has already been condensed into summary,
    crystallized into permanent memories, and distilled into narrative
    episodes — so deleting raw lines doesn't lose knowledge.
    """
    if not os.path.exists(ARCHIVE_PATH):
        return
    try:
        with open(ARCHIVE_PATH) as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(ARCHIVE_PATH, "w") as f:
                f.writelines(lines[-keep_lines:])
            logger.info("Archive truncated: %d → %d lines", len(lines), keep_lines)
    except Exception:
        logger.warning("Archive truncation failed", exc_info=True)
