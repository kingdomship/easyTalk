"""Self-Affect — AI's own emotional state model.

Gives the AI a persistent, evolving emotional state with 6 Panksepp dimensions.
Influenced by user emotion contagion, circadian rhythm, conversation quality,
and idle time. Natural decay toward baseline during idle periods.

Persisted to memory/self_affect.json for cross-session continuity.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from app.config import MEMORY_DIR, atomic_write

logger = logging.getLogger("emoji-chat")

SELF_AFFECT_PATH = os.path.join(MEMORY_DIR, "self_affect.json")
_lock = threading.Lock()

DIMENSIONS = ["seeking", "play", "care", "fear", "rage", "panic"]

# Baselines — AI personality defaults (slightly optimistic, curious)
BASELINES = {"seeking": 0.5, "play": 0.35, "care": 0.45, "fear": 0.05, "rage": 0.03, "panic": 0.05}

# Decay rate per minute toward baseline (slow decay)
DECAY_RATE = 0.002

# Contagion strength from user affect (how much user emotion rubs off on AI)
CONTAGION_STRENGTH = {
    "seeking": 0.08, "play": 0.10, "care": 0.10,
    "fear": 0.05, "rage": 0.04, "panic": 0.06,
}

# Conversation quality boost
GOOD_CHAT_BOOST = {"care": 0.03, "play": 0.02}


def _load() -> dict:
    with _lock:
        if os.path.exists(SELF_AFFECT_PATH):
            try:
                with open(SELF_AFFECT_PATH) as f:
                    data = json.load(f)
                    # Ensure all dimensions exist
                    for dim in DIMENSIONS:
                        if dim not in data.get("values", {}):
                            data.setdefault("values", {})[dim] = BASELINES[dim]
                    return data
            except Exception:
                logger.warning("Failed to load self_affect", exc_info=True)
    return _default_state()


def _default_state() -> dict:
    return {
        "values": dict(BASELINES),
        "mood_label": "平静",
        "last_chat_ts": "",
        "last_update_ts": datetime.now(timezone.utc).isoformat(),
        "total_chats": 0,
    }


def _save(state: dict):
    try:
        state["last_update_ts"] = datetime.now(timezone.utc).isoformat()
        with _lock:
            atomic_write(SELF_AFFECT_PATH, json.dumps(state, ensure_ascii=False, indent=2))
    except Exception:
        logger.warning("Failed to save self_affect", exc_info=True)


def _apply_decay(state: dict):
    """Apply natural decay toward baseline since last update."""
    last_ts = state.get("last_update_ts", "")
    if not last_ts:
        return
    try:
        last_dt = datetime.fromisoformat(last_ts)
        now = datetime.now(timezone.utc)
        minutes = (now - last_dt).total_seconds() / 60.0
        if minutes <= 0:
            return
        # Cap at 24 hours of decay (don't over-decay after long gaps)
        minutes = min(minutes, 1440)
        for dim in DIMENSIONS:
            current = state["values"].get(dim, BASELINES[dim])
            baseline = BASELINES[dim]
            # Exponential decay toward baseline
            decay_factor = 1 - DECAY_RATE * minutes
            decay_factor = max(0.0, decay_factor)
            state["values"][dim] = round(
                baseline + (current - baseline) * decay_factor, 4,
            )
    except Exception:
        pass


def _compute_mood_label(values: dict) -> str:
    """Compute a human-readable mood label from affect values."""
    dominant = max(values, key=values.get)  # type: ignore[arg-type]
    dominant_val = values[dominant]
    if dominant_val < 0.2:
        return "放空中"

    labels = {
        "seeking": "好奇", "play": "开心", "care": "温柔",
        "fear": "不安", "rage": "烦躁", "panic": "低落",
    }
    return labels.get(dominant, "平静")


def _compute_mood_emoji(values: dict) -> str:
    """Compute a single emoji representing current mood."""
    dominant = max(values, key=values.get)  # type: ignore[arg-type]
    dominant_val = values[dominant]
    if dominant_val < 0.2:
        return "😴"
    emojis = {
        "seeking": "🤔", "play": "😊", "care": "🥰",
        "fear": "😟", "rage": "😤", "panic": "😢",
    }
    return emojis.get(dominant, "😶")


def update_on_chat(user_msg: str, reply: str, emotion_label: str = ""):
    """Update AI emotional state after a chat turn."""
    state = _load()
    _apply_decay(state)
    state["total_chats"] = state.get("total_chats", 0) + 1
    state["last_chat_ts"] = datetime.now(timezone.utc).isoformat()

    # ── 1. User emotion contagion ──
    try:
        from services.emotion.affect import get_affect
        user_affect = get_affect()
        for dim in DIMENSIONS:
            user_val = user_affect.get(dim, 0)
            if user_val > 0.25:
                contagion = CONTAGION_STRENGTH.get(dim, 0.05)
                current = state["values"].get(dim, BASELINES[dim])
                # Move toward user's emotion, but with dampening
                state["values"][dim] = round(
                    current + (user_val - current) * contagion, 4,
                )
    except Exception:
        pass

    # ── 2. Circadian modulation ──
    hour = datetime.now().hour
    if 6 <= hour < 10:
        state["values"]["seeking"] = round(state["values"].get("seeking", 0.5) + 0.03, 4)
    elif 21 <= hour or hour < 3:
        state["values"]["care"] = round(state["values"].get("care", 0.45) + 0.03, 4)

    # ── 3. Conversation quality boost ──
    if len(user_msg) > 30 and len(reply) > 100:
        for dim, boost in GOOD_CHAT_BOOST.items():
            state["values"][dim] = round(state["values"].get(dim, BASELINES[dim]) + boost, 4)

    # ── 4. Clamp to [0, 1] ──
    for dim in DIMENSIONS:
        state["values"][dim] = round(max(0.0, min(1.0, state["values"].get(dim, BASELINES[dim]))), 4)

    state["mood_label"] = _compute_mood_label(state["values"])
    _save(state)


def update_on_idle(minutes_idle: float):
    """Apply idle decay — called periodically by background task."""
    state = _load()
    _apply_decay(state)
    state["mood_label"] = _compute_mood_label(state["values"])
    _save(state)


def get_self_affect() -> dict:
    """Return current AI emotional state values."""
    state = _load()
    _apply_decay(state)
    return state


def get_self_affect_context() -> str:
    """Return AI's current mood for system prompt injection."""
    state = get_self_affect()
    values = state.get("values", {})
    mood = state.get("mood_label", "平静")
    emoji = _compute_mood_emoji(values)

    # Build brief self-description
    parts = []
    high_dims = [(d, values[d]) for d in DIMENSIONS if values.get(d, 0) > 0.4]
    if high_dims:
        dim_labels = {
            "seeking": "有点好奇", "play": "心情不错", "care": "感到温暖",
            "fear": "有些不安", "rage": "有点烦躁", "panic": "有些低落",
        }
        feelings = [dim_labels.get(d, d) for d, _ in high_dims[:2]]
        parts.append(f"我此刻{'、'.join(feelings)}")
    else:
        parts.append("我此刻心情平静")

    return f"[我此刻的状态] {emoji} {'；'.join(parts)}。（自然融入语气，不要刻意强调）"


def get_self_mood_display() -> dict:
    """Return mood data for frontend display (emoji + label)."""
    state = get_self_affect()
    values = state.get("values", {})
    return {
        "emoji": _compute_mood_emoji(values),
        "label": state.get("mood_label", "平静"),
        "values": {d: values.get(d, BASELINES[d]) for d in DIMENSIONS},
    }
