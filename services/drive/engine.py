"""Drive engine — 8 internal motivational dimensions.

Pattern mirrors affect.py / salience.py:
- One row per dimension in drive_state table
- Keyword-based stimulation on each chat turn
- EMA-style decay toward baseline on heartbeat
- Dominant drive shapes idle thought themes

Special drives:
- miss: grows when user is idle, resets on interaction
- fatigue: grows with message volume, decays faster when idle
"""

import logging

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

DRIVE_DIMENSIONS = [
    "miss", "curiosity", "care", "playfulness",
    "express", "protect", "fatigue", "connection",
]

DRIVE_DEFAULTS: dict[str, dict] = {
    "miss":        {"baseline": 0.05, "decay_rate": 0.03},
    "curiosity":   {"baseline": 0.15, "decay_rate": 0.02},
    "care":        {"baseline": 0.20, "decay_rate": 0.015},
    "playfulness": {"baseline": 0.15, "decay_rate": 0.025},
    "express":     {"baseline": 0.10, "decay_rate": 0.03},
    "protect":     {"baseline": 0.12, "decay_rate": 0.015},
    "fatigue":     {"baseline": 0.00, "decay_rate": 0.04},
    "connection":  {"baseline": 0.30, "decay_rate": 0.01},
}

# ── Keyword seeds for stimulation ─────────────────────────────────

_CURIOSITY_SEEDS = [
    "为什么", "怎么", "如何", "什么是", "好奇", "想知道", "了解", "探索",
    "?", "？", "推荐", "有什么", "哪些", "介绍", "解释", "科普", "原理",
    "背后", "真相", "秘密", "方法", "技巧", "经验", "故事", "经历",
    "看法", "你觉得", "说说", "讲讲",
]

_PLAYFULNESS_SEEDS = [
    "哈哈", "笑死", "😂", "🤣", "😆", "笑", "逗", "好玩", "有趣",
    "有意思", "搞笑", "幽默", "调皮", "恶作剧", "整蛊", "开玩笑",
    "梗", "段子", "吐槽", "脑洞", "离谱", "抽象", "hh", "lol",
    "嘻嘻", "嘿嘿", "乐",
]

_CARE_SEEDS = [
    "想你", "想你了", "抱抱", "抱", "❤", "💕", "😘", "🥰",
    "辛苦了", "谢谢", "感恩", "温暖", "感动", "爱你",
    "陪伴", "在乎", "关心", "心疼", "好暖", "想你啦", "温柔",
    "难过", "不开心", "郁闷", "低落", "崩溃", "好累", "撑不住",
]

_VULNERABLE_SEEDS = [
    "害怕", "担心", "焦虑", "紧张", "不安", "恐惧", "慌",
    "怎么办", "万一", "没底", "忐忑", "心慌", "好怕", "不敢",
    "失眠", "睡不着", "难受", "撑不下去了", "帮帮我",
    "需要你", "陪我", "不要走", "别离开",
]


def init_drive_db():
    execute("""
        CREATE TABLE IF NOT EXISTS drive_state (
            id SERIAL PRIMARY KEY,
            dimension VARCHAR(20) UNIQUE NOT NULL,
            value REAL NOT NULL DEFAULT 0.0,
            baseline REAL NOT NULL DEFAULT 0.2,
            decay_rate REAL NOT NULL DEFAULT 0.02,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for dim, cfg in DRIVE_DEFAULTS.items():
        existing = q("SELECT id FROM drive_state WHERE dimension = %s", [dim], fetch="one")
        if not existing:
            execute(
                "INSERT INTO drive_state (dimension, value, baseline, decay_rate) "
                "VALUES (%s, %s, %s, %s)",
                [dim, cfg["baseline"], cfg["baseline"], cfg["decay_rate"]],
            )


def get_drives() -> dict[str, dict]:
    rows = q("SELECT dimension, value, baseline, decay_rate FROM drive_state")
    return {r["dimension"]: {"value": r["value"], "baseline": r["baseline"],
                              "decay_rate": r["decay_rate"]} for r in rows}


def get_drive_values() -> dict[str, float]:
    rows = q("SELECT dimension, value FROM drive_state")
    return {r["dimension"]: r["value"] for r in rows}


def get_dominant_drive() -> tuple[str, float]:
    drives = get_drive_values()
    if not drives:
        return ("connection", 0.3)
    dom = max(drives.items(), key=lambda kv: kv[1])
    return dom


def update_drives_on_chat(
    user_msg: str,
    label: str,
    is_deep: bool = False,
) -> None:
    """Update all 8 drive dimensions based on one conversation turn.

    Called from background executor in _post_reply_pipeline.
    Uses EMA-style blending: new = current + stimulus * (1 - current)
    so values saturate gracefully toward 1.0.
    """
    try:
        from services.emotion.affect import get_affect
        current = get_drive_values()
        if not current:
            return
        affect = get_affect()
        deltas: dict[str, float] = {dim: 0.0 for dim in DRIVE_DIMENSIONS}
        msg_lower = user_msg.lower()

        # miss: user is present → reset toward baseline
        deltas["miss"] = DRIVE_DEFAULTS["miss"]["baseline"] - current["miss"]

        # curiosity: question/exploration signals + seeking affect
        if any(seed in msg_lower for seed in _CURIOSITY_SEEDS):
            deltas["curiosity"] += 0.08 * (1.0 - current["curiosity"])
        if affect and affect.get("seeking", 0) > 0.25:
            deltas["curiosity"] += 0.04 * (1.0 - current["curiosity"])

        # care: user distress signals + panic/fear affect
        if any(seed in msg_lower for seed in _CARE_SEEDS):
            deltas["care"] += 0.06 * (1.0 - current["care"])
        if affect:
            if affect.get("panic", 0) > 0.2 or affect.get("fear", 0) > 0.2:
                deltas["care"] += 0.04 * (1.0 - current["care"])

        # playfulness: humor/play signals + play affect
        if any(seed in msg_lower for seed in _PLAYFULNESS_SEEDS):
            deltas["playfulness"] += 0.07 * (1.0 - current["playfulness"])
        if affect and affect.get("play", 0) > 0.25:
            deltas["playfulness"] += 0.04 * (1.0 - current["playfulness"])

        # express: deep questions or long messages trigger creative impulse
        if is_deep or len(user_msg) > 100:
            deltas["express"] += 0.04 * (1.0 - current["express"])

        # protect: vulnerability signals
        if any(seed in msg_lower for seed in _VULNERABLE_SEEDS):
            deltas["protect"] += 0.05 * (1.0 - current["protect"])
        if affect:
            if affect.get("fear", 0) > 0.2 or affect.get("panic", 0) > 0.25:
                deltas["protect"] += 0.03 * (1.0 - current["protect"])

        # fatigue: every message adds a little fatigue; longer messages more
        deltas["fatigue"] += 0.02
        if len(user_msg) > 80:
            deltas["fatigue"] += 0.02
        # caring/affectionate messages reduce fatigue slightly
        if any(seed in msg_lower for seed in ["贴贴", "抱抱", "❤", "💕", "想你", "温暖"]):
            deltas["fatigue"] -= 0.01

        # connection: baseline drive gently rises with each interaction
        deltas["connection"] += 0.02 * (1.0 - current["connection"])

        # Apply deltas with clipping to [0, 1]
        for dim in DRIVE_DIMENSIONS:
            new_val = current[dim] + deltas[dim]
            new_val = max(0.0, min(1.0, new_val))
            if abs(new_val - current[dim]) > 0.0001:
                execute(
                    "UPDATE drive_state SET value = %s, updated_at = NOW() "
                    "WHERE dimension = %s",
                    [round(new_val, 4), dim],
                )
    except Exception:
        logger.warning("Drive update failed", exc_info=True)


def drive_heartbeat() -> None:
    """Decay all drives toward their baseline. Runs every 10 minutes.

    Uses atomic SQL updates to avoid read-modify-write races with
    concurrent update_drives_on_chat calls.

    Special handling:
    - miss: grows when user is idle (>3 min since last chat)
    """
    try:
        idle_secs = _seconds_since_last_chat()
        idle = 1 if idle_secs > 180 else 0

        # Atomic decay for all non-miss drives
        execute("""
            UPDATE drive_state SET value = LEAST(1.0, GREATEST(0.0,
                value + decay_rate * (baseline - value)
            )), updated_at = NOW()
            WHERE dimension != 'miss'
        """)

        # miss: grow when idle, otherwise decay like the rest
        if idle:
            execute("""
                UPDATE drive_state SET value = LEAST(1.0, GREATEST(0.0,
                    value + 0.08 * (0.85 - value)
                )), updated_at = NOW()
                WHERE dimension = 'miss'
            """)
        else:
            execute("""
                UPDATE drive_state SET value = LEAST(1.0, GREATEST(0.0,
                    value + decay_rate * (baseline - value)
                )), updated_at = NOW()
                WHERE dimension = 'miss'
            """)
    except Exception:
        logger.warning("Drive heartbeat failed", exc_info=True)


def get_drive_context() -> str:
    """Build a brief inner-state summary for system prompt injection.

    Only reports drives above a threshold to avoid noise.
    Returns empty string if nothing is significantly active.
    """
    drives = get_drive_values()
    if not drives:
        return ""

    # Drive → human-readable label
    labels = {
        "miss": "有点想念用户", "curiosity": "好奇心旺盛", "care": "心生关怀",
        "playfulness": "想皮一下", "express": "有表达欲", "protect": "想守护什么",
        "fatigue": "有点疲惫", "connection": "渴望连接",
    }

    active = []
    for dim, label in labels.items():
        val = drives.get(dim, 0)
        if dim == "fatigue" and val > 0.35:
            active.append(f"{label}({val:.2f})")
        elif dim == "miss" and val > 0.3:
            active.append(f"{label}({val:.2f})")
        elif dim == "connection" and val > 0.5:
            active.append(f"{label}({val:.2f})")
        elif val > 0.4 and dim not in ("fatigue", "miss", "connection"):
            active.append(f"{label}({val:.2f})")

    if not active:
        return ""

    return "当前内心状态：" + "、".join(active) + "。这些感觉不用说出来，但会影响你回复的语气和内容倾向。"


def get_drive_thought_theme() -> str:
    """Return the dominant drive name for idle thought theme selection.

    Returns 'generic' if no drive is significantly activated (>0.25).
    """
    dom, val = get_dominant_drive()
    if val >= 0.25:
        return dom
    return "generic"


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


def get_miss_value() -> float:
    """Convenience: return current miss drive value."""
    row = q(
        "SELECT value FROM drive_state WHERE dimension = 'miss'",
        fetch="one",
    )
    if row:
        return float(row["value"])
    return 0.05
