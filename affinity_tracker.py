"""6D affinity tracking — warmth, trust, intimacy, curiosity, patience, tension.

Updated after each conversation turn using EMA smoothing.
Persisted in DB for survival across restarts.
"""

import json
from db import q, execute, init_db

DIMENSIONS = ["warmth", "trust", "intimacy", "curiosity", "patience", "tension"]
DEFAULTS = {"warmth": 0.5, "trust": 0.4, "intimacy": 0.2, "curiosity": 0.6, "patience": 0.7, "tension": 0.1}
EMA_ALPHA = 0.05  # Smoothing factor — small = slow change


def init_affinity_db():
    execute("""
        CREATE TABLE IF NOT EXISTS affinity (
            id SERIAL PRIMARY KEY,
            dimension VARCHAR(20) UNIQUE NOT NULL,
            value REAL NOT NULL DEFAULT 0.5,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # Seed defaults if empty
    for dim in DIMENSIONS:
        existing = q("SELECT id FROM affinity WHERE dimension = %s", [dim], fetch="one")
        if not existing:
            execute("INSERT INTO affinity (dimension, value) VALUES (%s, %s)", [dim, DEFAULTS[dim]])


def get_affinity() -> dict:
    """Return current affinity values."""
    rows = q("SELECT dimension, value FROM affinity")
    result = {}
    for r in rows:
        result[r["dimension"]] = round(r["value"], 3)
    return result


def update_affinity(user_msg: str, emotion_label: str):
    """Update affinity based on user message sentiment and avatar emotion.

    Simple heuristic — could be replaced with LLM-based analysis.
    """
    current = get_affinity()
    if not current:
        init_affinity_db()
        current = dict(DEFAULTS)

    msg_lower = user_msg.lower()

    # Heuristic adjustments based on keywords and emotion
    deltas = {d: 0.0 for d in DIMENSIONS}

    # Positive signals
    if any(w in msg_lower for w in ["开心", "哈哈", "谢谢", "喜欢", "好棒", "爱", "想你了", "miss you"]):
        deltas["warmth"] += 0.03
        deltas["trust"] += 0.02
        deltas["intimacy"] += 0.04
        deltas["tension"] -= 0.03

    # Negative / venting
    if any(w in msg_lower for w in ["难过", "生气", "烦", "讨厌", "累死了", "崩溃"]):
        deltas["trust"] += 0.03  # User trusts enough to vent
        deltas["patience"] += 0.02
        deltas["tension"] += 0.02

    # Question / curiosity
    if any(w in msg_lower for w in ["?", "？", "什么", "怎么", "为什么"]):
        deltas["curiosity"] += 0.02

    # Long message = engaged
    if len(user_msg) > 30:
        deltas["intimacy"] += 0.01
        deltas["warmth"] += 0.01

    # Natural decay (time passing)
    deltas["tension"] -= 0.005
    deltas["patience"] -= 0.002

    # Apply EMA smoothing
    for dim in DIMENSIONS:
        old_val = current.get(dim, DEFAULTS[dim])
        new_val = old_val + deltas[dim]
        # Clamp 0-1
        new_val = max(0.0, min(1.0, new_val))
        execute(
            "UPDATE affinity SET value = %s, updated_at = NOW() WHERE dimension = %s",
            [round(new_val, 4), dim],
        )


def get_affinity_context() -> str:
    """Return a brief affinity description to inject into system prompt."""
    aff = get_affinity()
    if not aff:
        return ""

    # Only include if relationship has developed beyond defaults
    if aff.get("warmth", 0.5) > 0.55 or aff.get("intimacy", 0.2) > 0.25:
        level = "熟悉"
        if aff.get("intimacy", 0) > 0.5:
            level = "非常亲密"
        elif aff.get("warmth", 0) > 0.6:
            level = "温暖默契"

        return (
            f"当前关系状态：{level}（亲密度{aff['intimacy']:.2f}，温暖度{aff['warmth']:.2f}，"
            f"信任度{aff['trust']:.2f}）。"
            f"根据关系深浅自然调整你的语气和调侃尺度。"
        )
    return ""
