"""Persona Decision Engine — rules-first action selection for proactive behavior.

Inspired by eros-engine's PDE: deterministic thresholds determine whether
the AI should stay silent, generate an idle thought, or proactively reach out.
LLM is only called to generate the actual message, not to make the decision.

Decision factors:
- Drives (miss, connection)
- Idle time since last user message
"""

import logging

logger = logging.getLogger("emoji-chat")

# ── Decision thresholds ──────────────────────────────────────────

_ACTIVE_GREETING_IDLE_MIN = 30   # minutes idle before considering active greeting
_ACTIVE_GREETING_MISS_MIN = 0.30  # miss reaches ~0.28 at 30min idle, ~0.40 at 60min
_ACTIVE_GREETING_CONN_MIN = 0.55
_ACTIVE_GREETING_CONN_IDLE_MIN = 60  # connection needs longer idle to trigger greeting

_PROMPTS: dict[str, str] = {
    "active_greeting": (
        "你是一个有内在生活的AI角色。用户已经离线了一段时间，你很想念ta。\n"
        "请生成一句温暖自然的主动问候（30-60字），像一个朋友发现对方上线时的自然招呼。\n"
        "可以提到：最近想到的事、关心对方的近况、或者分享一个小小的想法。\n"
        "语气轻松自然，不要过于热烈或夸张。直接输出内容，不要JSON和引号。"
    ),
}


def decide_action(
    drives: dict[str, float] | None = None,
    idle_minutes: float = 0,
) -> str:
    """Decide what action the AI should take while the user is away.

    Returns one of: "silent", "idle_thought", "active_greeting"

    Decision priority (rules-first, deterministic):
    1. active_greeting: miss drive high + long idle, OR connection high + very long idle
    2. idle_thought: any drive > 0.25 + idle > 3min (existing behavior)
    3. silent: none of the above
    """
    if not drives:
        return "silent"

    miss = drives.get("miss", 0)
    connection = drives.get("connection", 0)

    # Active greeting: AI proactively reaches out
    if idle_minutes >= _ACTIVE_GREETING_IDLE_MIN:
        if miss >= _ACTIVE_GREETING_MISS_MIN:
            logger.info("PDE → active_greeting (miss=%.2f, idle=%.0fm)", miss, idle_minutes)
            return "active_greeting"
        if connection >= _ACTIVE_GREETING_CONN_MIN and idle_minutes >= _ACTIVE_GREETING_CONN_IDLE_MIN:
            logger.info("PDE → active_greeting (connection=%.2f, idle=%.0fm)",
                        connection, idle_minutes)
            return "active_greeting"

    # Idle thought: any drive active + minimum idle
    if idle_minutes >= 3:
        if any(drives.get(d, 0) > 0.25 for d in drives):
            return "idle_thought"

    return "silent"


def get_action_prompt(action: str) -> str | None:
    """Return the prompt template for a given action, or None if not found."""
    return _PROMPTS.get(action)
