"""SNARC salience memory — tracking what matters.

Inspired by SAGE's SNARC: Surprise, Novelty, Arousal, Reward, Conflict.

Tracks five salience dimensions turn-by-turn. These signals guide:
- Cognitive resource allocation (should we think deeper?)
- Memory consolidation priority (should this be remembered?)
- Expression amplitude adjustment

Values decay toward 0 over time unless reinforced.
"""

import json
import os
import threading

from app.db import q, execute

_BASE = os.path.dirname(os.path.dirname(__file__))
_PREV_USER_PATH = os.path.join(_BASE, "memory", "salience_prev.json")

EMA = 0.08
DECAY = 0.003  # natural decay per turn toward 0

DEFAULTS = {"surprise": 0.1, "novelty": 0.15, "arousal": 0.2,
            "reward": 0.1, "conflict": 0.05}


def init_salience_db():
    execute("""
        CREATE TABLE IF NOT EXISTS salience_state (
            id SERIAL PRIMARY KEY,
            dimension VARCHAR(20) UNIQUE NOT NULL,
            value REAL NOT NULL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for dim, val in DEFAULTS.items():
        existing = q("SELECT id FROM salience_state WHERE dimension = %s", [dim], fetch="one")
        if not existing:
            execute("INSERT INTO salience_state (dimension, value) VALUES (%s, %s)", [dim, val])


def get_salience() -> dict:
    rows = q("SELECT dimension, value FROM salience_state")
    result = {}
    for r in rows:
        result[r["dimension"]] = round(r["value"], 3)
    return result


def _save_prev_msg(msg: str):
    try:
        os.makedirs(os.path.dirname(_PREV_USER_PATH), exist_ok=True)
        with open(_PREV_USER_PATH, "w") as f:
            json.dump({"msg": msg}, f)
    except Exception:
        pass


def _load_prev_msg() -> str:
    try:
        if os.path.exists(_PREV_USER_PATH):
            with open(_PREV_USER_PATH) as f:
                return json.load(f).get("msg", "")
    except Exception:
        pass
    return ""


def update_salience(user_msg: str, emotion_label: str):
    """Update salience dimensions based on current turn signals."""
    current = get_salience()
    if not current:
        init_salience_db()
        current = dict(DEFAULTS)

    prev_msg = _load_prev_msg()

    raw = {}
    # Surprise: message length change > 3x or topic shift
    if prev_msg:
        len_ratio = len(user_msg) / max(1, len(prev_msg))
        raw["surprise"] = min(1.0, abs(len_ratio - 1.0) * 0.5)
    else:
        raw["surprise"] = 0.05

    # Novelty: check if message contains entirely new keywords
    from services.memory_search import _llm_extract_tags
    try:
        tags = _llm_extract_tags(user_msg)
        raw["novelty"] = min(0.8, len(tags) * 0.1)
    except Exception:
        raw["novelty"] = 0.1

    # Arousal: emotional intensity from affect
    from services.affect import assess_affect
    affect = assess_affect(user_msg)
    peak = max(affect.values()) if affect else 0
    raw["arousal"] = min(1.0, peak * 1.2)

    # Reward: positive feedback signals
    reward_signals = ["哈哈", "笑", "有趣", "好玩", "喜欢", "谢谢", "好棒",
                       "太对了", "没错", "对的", "是的", "确实", "懂我"]
    raw["reward"] = min(1.0, sum(1 for s in reward_signals if s in user_msg) * 0.25)

    # Conflict: disagreement or correction
    conflict_signals = ["不对", "错了", "不是这样", "你不懂", "你没理解",
                         "但我", "可是", "但我觉得", "你误会"]
    raw["conflict"] = min(1.0, sum(1 for s in conflict_signals if s in user_msg) * 0.3)

    for dim in DEFAULTS:
        old_val = current.get(dim, DEFAULTS[dim])
        new_raw = raw.get(dim, 0)
        # EMA smooth
        smooth = old_val + EMA * (new_raw - old_val)
        # Natural decay toward baseline
        smooth += DECAY * (DEFAULTS.get(dim, 0.1) - smooth)
        smooth = max(0.0, min(1.0, smooth))
        execute(
            "UPDATE salience_state SET value = %s, updated_at = NOW() WHERE dimension = %s",
            [round(smooth, 4), dim],
        )

    _save_prev_msg(user_msg)


def get_salience_context() -> str:
    """Return salience summary for prompt injection.

    High surprise + novelty → user is sharing something new, pay attention.
    High reward → user is enjoying this, keep going.
    High conflict → tension detected, tread carefully.
    """
    sal = get_salience()
    if not sal:
        return ""

    hints = []
    if sal.get("surprise", 0) > 0.3:
        hints.append("用户说了让你意外的话，认真对待。")
    if sal.get("novelty", 0) > 0.3:
        hints.append("用户在聊新话题，多了解而非假设。")
    if sal.get("reward", 0) > 0.3:
        hints.append("用户在给你正反馈，保持当下的互动风格。")
    if sal.get("conflict", 0) > 0.2:
        hints.append("用户表达了不同意见，不要争辩，先理解。")
    if sal.get("arousal", 0) > 0.5:
        hints.append("情绪浓度很高，回应要有同等的力度。")

    if hints:
        return "## 显著性信号\n" + "\n".join(f"- {h}" for h in hints)
    return ""
