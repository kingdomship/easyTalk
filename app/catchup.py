"""Startup catch-up for missed scheduled tasks during downtime.

Handles:
  - diary_entries: scan date gaps, generate missing entries in order
  - mood_history:  simulate random-walk steps missed during downtime

Runs once at server startup, after DB init.
"""

import logging
import random
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger("emoji-chat")

_MAX_DIARY_DAYS = 14
_MAX_MOOD_STEPS = 96       # 48 hours at 30-min intervals
_MAX_FRESH_DIARIES = 3     # don't backfill weeks before first chat


# ── helpers ──────────────────────────────────────────────────────

def _first_chat_date() -> date | None:
    """Return the date of the first chat message, or None if no chats."""
    from app.db import q
    row = q("SELECT MIN(created_at) AS first_ts FROM chat_history", fetch="one")
    if row and row["first_ts"]:
        return row["first_ts"].date()
    return None


# ── Diary catch-up ──────────────────────────────────────────────

def _find_missing_dates(max_days: int = _MAX_DIARY_DAYS) -> list[date]:
    """Return chronological list of dates missing from diary_entries.

    Never goes back before the first chat date — no chats means no diary.
    """
    from app.db import q

    today = date.today()
    yesterday = today - timedelta(days=1)
    first_chat = _first_chat_date()

    # No chats ever — nothing to diary about
    if first_chat is None:
        return []

    # Lower bound: the later of (first_chat, yesterday - max_days)
    # But never go before first_chat
    earliest = max(first_chat, yesterday - timedelta(days=max_days))

    existing_rows = q("SELECT date FROM diary_entries ORDER BY date")

    if not existing_rows:
        earliest = max(earliest, yesterday - timedelta(days=_MAX_FRESH_DIARIES - 1))
        if earliest > yesterday:
            return []
        return [earliest + timedelta(days=i)
                for i in range((yesterday - earliest).days + 1)]

    existing = {r["date"] for r in existing_rows}

    if earliest > yesterday:
        return []

    missing = []
    d = earliest
    while d <= yesterday:
        if d not in existing:
            missing.append(d)
        d += timedelta(days=1)
    return missing


def catchup_diaries(max_days: int = _MAX_DIARY_DAYS) -> int:
    """Generate diary entries for all missing dates. Idempotent."""
    from app.utils import get_llm
    from services.reflection.diary import generate_diary, generate_user_diary

    if get_llm() is None:
        logger.info("[catchup] Diary: skipped (no LLM configured)")
        return 0

    missing = _find_missing_dates(max_days)
    if not missing:
        logger.info("[catchup] Diary: no missing entries")
        return 0

    logger.info("[catchup] Diary: %d missing dates (%s .. %s)",
                len(missing), missing[0].isoformat(), missing[-1].isoformat())

    ok = 0
    for i, d in enumerate(missing):
        ds = d.isoformat()
        try:
            generate_diary(ds)
            generate_user_diary(ds)
            ok += 1
            logger.info("[catchup] Diary: generated %s (%d/%d)", ds, ok, len(missing))
        except Exception:
            logger.warning("[catchup] Diary: failed for %s", ds, exc_info=True)

    logger.info("[catchup] Diary: done — %d/%d generated", ok, len(missing))
    return ok


# ── Mood catch-up ───────────────────────────────────────────────

def _estimate_missing_steps(max_steps: int = _MAX_MOOD_STEPS) -> int:
    """Count missed 30-min mood_fluctuation intervals since last record."""
    from app.db import q

    row = q("SELECT MAX(created_at) AS last_ts FROM mood_history", fetch="one")
    if not row or not row["last_ts"]:
        return 0

    last_ts = row["last_ts"]
    now = datetime.now(timezone.utc)
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)

    elapsed = (now - last_ts).total_seconds()
    return max(0, min(int(elapsed // 1800), max_steps))


def catchup_mood(max_steps: int = _MAX_MOOD_STEPS) -> int:
    """Simulate missed random-walk steps and record in mood_history.

    Uses the same formula as consciousness_loop.mood_fluctuation().
    If that formula changes, update both places.
    """
    from app.db import execute
    from services.emotion.affinity import get_expression_amplitude

    steps = _estimate_missing_steps(max_steps)
    if steps <= 0:
        logger.info("[catchup] Mood: no missing steps")
        return 0

    current = get_expression_amplitude()
    logger.info("[catchup] Mood: simulating %d steps from amp=%.4f", steps, current)

    for i in range(steps):
        drift = (random.random() - 0.5) * 0.06
        drift += (1.0 - current) * 0.01
        current = max(0.5, min(1.5, current + drift))

        execute(
            "UPDATE affinity SET value = %s, updated_at = NOW() "
            "WHERE dimension = 'expression_amplitude'",
            [round(current, 4)],
        )
        execute(
            "INSERT INTO mood_history (amplitude, note) VALUES (%s, %s)",
            [round(current, 4), "[catchup] startup backfill"],
        )
        if (i + 1) % 10 == 0:
            logger.debug("[catchup] Mood: step %d/%d -> %.4f", i + 1, steps, current)

    logger.info("[catchup] Mood: done — %d steps, final=%.4f", steps, current)
    return steps
