"""Bidirectional emotion contagion modeling.

Tracks how the AI's expressed emotions correlate with subsequent changes in
the user's emotional state (lag-1). Also measures the effectiveness of the
comfort mode — is the user's distress actually decreasing?

Pure numerical tracking — zero extra LLM calls. Updates each turn from
_post_reply_pipeline, injects strategy hints via _build_context.
"""

import json
import logging
import os
import threading

from app.config import MEMORY_DIR, atomic_write

logger = logging.getLogger("emoji-chat")

CONTAGION_PATH = os.path.join(MEMORY_DIR, "contagion_state.json")

_lock = threading.Lock()

# Emotion labels → contagion categories
# Positive expressions: joyful, loving, amused, playful, proud, grateful, hopeful
# Neutral: neutral, calm, thoughtful, curious
# Negative: sad, anxious, apologetic, worried, sheepish

_POSITIVE_LABELS = {"joyful", "loving", "amused", "playful", "proud", "grateful",
                    "hopeful", "excited", "surprised", "warm", "affectionate",
                    "happy", "cheerful", "enthusiastic", "inspired", "touched",
                    "relieved", "satisfied"}
_NEGATIVE_LABELS = {"sad", "anxious", "apologetic", "worried", "sheepish",
                    "guilty", "embarrassed", "concerned", "sympathetic",
                    "sorrowful", "melancholy", "nervous", "upset"}


def _label_category(label: str) -> str:
    """Map emotion label to contagion category."""
    label_lower = label.lower().strip()
    if label_lower in _POSITIVE_LABELS:
        return "positive"
    if label_lower in _NEGATIVE_LABELS:
        return "negative"
    return "neutral"


# ── State persistence ──────────────────────────────────────────────────

def _load_state() -> dict:
    if os.path.exists(CONTAGION_PATH):
        try:
            with open(CONTAGION_PATH) as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to load contagion state", exc_info=True)
    return {
        "last_ai_category": "neutral",
        "last_ai_label": "neutral",
        "last_user_neg": 0.0,
        # Track comfort effectiveness: (total_uses, times_improved, times_worsened)
        "comfort_stats": {"uses": 0, "improved": 0, "worsened": 0, "unchanged": 0},
        # EMA of contagion: positive_ai → user_neg_decrease, negative_ai → user_neg_increase
        "contagion_strength": 0.0,  # positive = AI emotions affect user as expected
    }


def _save_state(state: dict):
    try:
        atomic_write(CONTAGION_PATH, json.dumps(state, ensure_ascii=False, indent=2))
    except Exception:
        logger.warning("Failed to save contagion state", exc_info=True)


# ── Update per turn ────────────────────────────────────────────────────

def update_contagion(ai_label: str, user_affect: dict | None, mode: str):
    """Track emotional contagion from this turn.

    Called from _post_reply_pipeline. Compares current user affect with
    the previous turn's to measure the AI's emotional influence.

    Args:
        ai_label: The AI's expressed emotion label THIS turn (stored for next)
        user_affect: Current user Panksepp affect (updated from current msg)
        mode: Current behavioral mode (comfort/chat/deep/explore/play)
    """
    if user_affect is None:
        return

    with _lock:
        state = _load_state()
        # Use PREVIOUS turn's AI category (which actually influenced the user)
        prev_ai_cat = state.get("last_ai_category", "neutral")
        prev_mode = state.get("last_mode", "chat")
        current_neg = max(
            user_affect.get("panic", 0),
            user_affect.get("fear", 0),
            user_affect.get("rage", 0),
        )
        prev_neg = state.get("last_user_neg", 0.0)

        # Update contagion strength (EMA, alpha=0.05)
        # Expectation: positive AI → user neg decrease; negative AI → increase
        neg_delta = current_neg - prev_neg
        if prev_ai_cat == "positive" and neg_delta < -0.02:
            # Previous positive AI expression + user distress decreased → works
            state["contagion_strength"] = round(
                state.get("contagion_strength", 0.0) * 0.95 + 0.05, 4)
        elif prev_ai_cat == "positive" and neg_delta > 0.02:
            # Previous positive AI expression + user distress increased → not working
            state["contagion_strength"] = round(
                state.get("contagion_strength", 0.0) * 0.95 - 0.03, 4)
        elif prev_ai_cat == "negative" and neg_delta > 0.02:
            # Previous negative AI expression + user distress increased → expected
            pass  # neutral, this is normal mirroring
        else:
            # Decay toward 0
            state["contagion_strength"] = round(
                state.get("contagion_strength", 0.0) * 0.98, 4)

        # Track comfort mode effectiveness (previous mode, not current)
        if prev_mode == "comfort":
            cs = state.get("comfort_stats", {"uses": 0, "improved": 0, "worsened": 0, "unchanged": 0})
            cs["uses"] = cs.get("uses", 0) + 1
            if neg_delta < -0.03:
                cs["improved"] = cs.get("improved", 0) + 1
            elif neg_delta > 0.03:
                cs["worsened"] = cs.get("worsened", 0) + 1
            else:
                cs["unchanged"] = cs.get("unchanged", 0) + 1
            state["comfort_stats"] = cs

        # Store current values for next turn's comparison
        state["last_ai_category"] = _label_category(ai_label)
        state["last_ai_label"] = ai_label
        state["last_mode"] = mode
        state["last_user_neg"] = round(current_neg, 4)

        _save_state(state)


def get_contagion_context() -> str:
    """Generate strategy hints based on contagion effectiveness.

    Returns empty string unless comfort mode seems ineffective.
    """
    state = _load_state()
    cs = state.get("comfort_stats", {})
    total = cs.get("uses", 0)

    if total < 3:
        return ""

    improved = cs.get("improved", 0)
    worsened = cs.get("worsened", 0)
    effectiveness = improved / total if total > 0 else 0

    if effectiveness < 0.3 and total >= 3:
        return (
            "[情绪反馈] 最近几次安抚后用户的情绪似乎没有明显好转。"
            "可以试试不同的方式：有时候不急着安抚，只是安静地陪着，"
            "或者用一点幽默来转移注意力——可能比直接的安慰更有效。"
        )

    if effectiveness > 0.6:
        return (
            "[情绪反馈] 你最近的安抚方式似乎很有效，用户的情绪有在好转。"
            "保持这种节奏。"
        )

    return ""


def update_contagion_on_reply(ai_label: str, mode: str):
    """Called BEFORE building the next context (uses the CURRENT affect state).

    This records the previous AI response's emotional influence once we
    see the user's next message.
    """
    try:
        from services.emotion.affect import get_affect
        update_contagion(ai_label, get_affect(), mode)
    except Exception:
        logger.warning("Contagion update failed", exc_info=True)
