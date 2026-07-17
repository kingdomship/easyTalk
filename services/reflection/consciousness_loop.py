"""Background consciousness loop — idle thoughts and mood fluctuations.

Inspired by SAGE's continuous consciousness loop and Conscious MCP's
daydreaming system. The AI has an inner life even when the user isn't
actively chatting:

- idle_thought: every ~5 min when idle, generate a brief reflection
- mood_fluctuation: natural emotional drift every ~30 min
- diary_seed: accumulate idle thoughts into diary material

Idle thoughts are stored in DB and exposed via API for the frontend
to display when the user returns.
"""

import logging
import os
import random
from datetime import datetime, timezone

from app.db import q, execute
from app.utils import get_llm_model

logger = logging.getLogger("emoji-chat")

_IDLE_THOUGHT_PROMPT = """你是一个有内在生活的AI角色。用户现在不在，你正在独自思考。

请生成一句简短的内心独白（20-40字），内容可以是：
- 对最近聊天的回味
- 对星空的观察
- 一个突然想到的有趣念头
- 对用户的想念（但不过分依赖）

语气自然口语化，像一个人独处时的自言自语。
直接输出独白内容，不要JSON，不要引号包裹。"""


def init_loop_db():
    """Create tables for consciousness loop data."""
    execute("""
        CREATE TABLE IF NOT EXISTS idle_thoughts (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS mood_history (
            id SERIAL PRIMARY KEY,
            amplitude REAL NOT NULL DEFAULT 1.0,
            note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


def _seconds_since_last_chat() -> float:
    """Return seconds since the last user message."""
    row = q(
        "SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs "
        "FROM chat_history ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if row and row["secs"]:
        return float(row["secs"])
    return float("inf")


def _get_llm_client():
    from app.utils import get_llm, get_llm_model
    return get_llm()


def idle_thought():
    """Generate a brief idle thought if the user has been away for a while.

    Uses Persona Decision Engine to choose action type:
    - active_greeting: high miss/connection + long idle → proactive reach-out
    - idle_thought: any drive active + idle > 3min → internal monologue
    - silent: nothing significant → skip generation
    """
    secs = _seconds_since_last_chat()
    idle_min = secs / 60.0

    # ── PDE: decide what kind of thought (if any) to generate ──
    try:
        from services.cognition.pde import decide_action, get_action_prompt
        from services.drive.engine import get_drive_values
        drives = get_drive_values()
        action = decide_action(drives, idle_min)
        if action == "silent":
            return
    except Exception:
        action = "idle_thought"  # fallback to existing behavior
        drives = None

    # Check if we already generated a thought recently
    last_thought = q(
        "SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs "
        "FROM idle_thoughts ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    # Active greetings can be more frequent (every 10min); idle thoughts stay at 5min
    min_interval = 600 if action == "active_greeting" else 300
    if last_thought and last_thought["secs"] and float(last_thought["secs"]) < min_interval:
        return

    # ── Build prompt based on action type ──
    if action == "active_greeting":
        greeting_prompt = get_action_prompt("active_greeting")
        if greeting_prompt:
            system_prompt = greeting_prompt
        else:
            system_prompt = _IDLE_THOUGHT_PROMPT  # fallback
    else:
        # Existing drive-themed idle thought
        try:
            from services.drive.engine import get_drive_thought_theme
            from services.drive.prompts import THOUGHT_THEMES
            theme = get_drive_thought_theme()
            theme_prompt = THOUGHT_THEMES.get(theme, THOUGHT_THEMES["generic"])
        except Exception:
            theme_prompt = _IDLE_THOUGHT_PROMPT

        system_prompt = (
            f"你是一个有内在生活的AI角色。用户现在不在，你正在独自思考。\n\n"
            f"{theme_prompt}\n\n"
            f"请生成一句简短的内心独白（20-40字），内容围绕上述心情展开。\n"
            f"语气自然口语化，像一个人独处时的自言自语。\n"
            f"直接输出独白内容，不要JSON，不要引号包裹。"
        )

    try:
        client = _get_llm_client()
        if client is None:
            return
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "（星空安静地闪烁...）"},
            ],
            temperature=0.85,
            max_tokens=100 if action == "active_greeting" else 80,
        )
        content = resp.choices[0].message.content.strip()
        if content:
            prefix = "[主动]" if action == "active_greeting" else ""
            execute(
                "INSERT INTO idle_thoughts (content) VALUES (%s)",
                [f"{prefix}{content[:120]}"],
            )
            logger.info("Idle thought [%s]: %s", action, content[:60])
    except Exception:
        logger.warning("Operation failed", exc_info=True)


def mood_fluctuation():
    """Introduce slight natural drift in expression amplitude.

    Simulates the natural ebb and flow of mood when alone.
    """
    from services.emotion.affinity import get_expression_amplitude
    current = get_expression_amplitude()

    # Small random walk: ±0.03, biased toward neutral (1.0)
    drift = (random.random() - 0.5) * 0.06
    drift += (1.0 - current) * 0.01  # regression toward neutral
    new_val = max(0.5, min(1.5, current + drift))

    execute(
        "UPDATE affinity SET value = %s, updated_at = NOW() "
        "WHERE dimension = 'expression_amplitude'",
        [round(new_val, 4)],
    )
    execute(
        "INSERT INTO mood_history (amplitude, note) VALUES (%s, %s)",
        [round(new_val, 4), f"drift: {drift:+.3f}"],
    )


def diary_seed():
    """Merge accumulated idle thoughts into an inspiration seed for diary.

    Runs hourly. When enough idle thoughts have accumulated, uses LLM to
    merge them into a 30-60 word inspiration snippet that can later be
    injected into the no-chat diary prompt.
    """
    # Collect idle thoughts from the last 2 hours
    thoughts = q(
        "SELECT content FROM idle_thoughts "
        "WHERE EXTRACT(EPOCH FROM (NOW() - created_at)) < 7200 "
        "AND content NOT LIKE '[灵感]%' "
        "ORDER BY id DESC"
    )
    if len(thoughts) < 3:
        return

    # Check if we already seeded recently (within last 2 hours)
    last_seed = q(
        "SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs "
        "FROM idle_thoughts WHERE content LIKE '[灵感]%' "
        "ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if last_seed and last_seed["secs"] and float(last_seed["secs"]) < 7200:
        return

    combined = "\n".join([t["content"][:80] for t in thoughts[:5]])

    try:
        client = _get_llm_client()
        if client is None:
            return
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": "将以下零散的思绪合并成一段30-60字的灵感片段，像一个写日记前的随手笔记。用第一人称，自然口语化。直接输出，不要引号。"},
                {"role": "user", "content": combined},
            ],
            temperature=0.7,
            max_tokens=100,
        )
        seed = resp.choices[0].message.content.strip()
        if seed:
            execute(
                "INSERT INTO idle_thoughts (content) VALUES (%s)",
                [f"[灵感] {seed[:150]}"],
            )
            logger.info("Diary seed: %s", seed[:60])
    except Exception:
        logger.warning("Diary seed generation failed", exc_info=True)


def system2_consolidation():
    """Periodic integration of System 2 insights into System 1.

    Runs every ~30 min from the scheduler. Reads unapplied System 2
    insights and adjusts System 1 parameters accordingly.
    """
    from services.cognition.dual_system import system2_consolidation as _s2c
    _s2c()


def get_latest_idle_thought() -> str | None:
    """Return the most recent idle thought, if within the last hour."""
    row = q(
        "SELECT content FROM idle_thoughts "
        "WHERE EXTRACT(EPOCH FROM (NOW() - created_at)) < 3600 "
        "ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if row:
        return row["content"]
    return None
