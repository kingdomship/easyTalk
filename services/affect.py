"""Panksepp 7-system emotional assessment.

Evaluates user messages on 6 primary emotional dimensions (LUST excluded):
SEEKING, PLAY, CARE, FEAR, RAGE, PANIC/GRIEF.

Uses keyword seeds for efficiency — each dimension has curated Chinese
and English triggers. EMA smoothing (alpha=0.05) stored in DB.
"""

from app.db import q, execute

DIMENSIONS = ["seeking", "play", "care", "fear", "rage", "panic"]
DEFAULTS = {"seeking": 0.35, "play": 0.25, "care": 0.2, "fear": 0.1, "rage": 0.05, "panic": 0.1}
EMA_ALPHA = 0.05

# ── Keyword seeds ──────────────────────────────────────────────
_SEEKING_SEEDS = [
    "为什么", "怎么", "如何", "什么是", "好奇", "想知道", "了解", "探索",
    "试试", "试一下", "教我", "讲讲", "说来听听", "怎么看", "如何看待",
    "意味着什么", "本质", "意义", "?", "？", "推荐", "有什么", "哪些",
    "介绍", "解释", "科普", "原理", "背后", "真相", "神奇", "秘密",
    "方法", "技巧", "经验", "故事", "经历", "看法", "你觉得",
]

_PLAY_SEEDS = [
    "哈哈", "笑死", "😂", "🤣", "😆", "笑", "逗", "好玩", "有趣",
    "有意思", "搞笑", "幽默", "调皮", "恶作剧", "整蛊", "开玩笑",
    "梗", "段子", "吐槽", "脑洞", "离谱", "抽象", "hh", "lol",
    "😂", "😏", "嘻嘻", "嘿嘿", "乐",
]

_CARE_SEEDS = [
    "想你", "想你了", "抱抱", "抱", "亲", "❤", "💕", "😘", "🥰",
    "想我", "辛苦了", "谢谢", "感恩", "温暖", "感动", "爱你",
    "贴贴", "摸摸", "陪伴", "在乎", "关心", "心疼", "好暖",
    "miss you", "想你啦", "温柔",
]

_FEAR_SEEDS = [
    "害怕", "担心", "焦虑", "紧张", "不安", "恐惧", "慌", "压力",
    "怎么办", "万一", "不确定", "没底", "忐忑", "心慌", "惶恐",
    "怕", "好怕", "不敢", "心虚", "失眠", "睡不着",
    "面试", "考试", "上台", "汇报", "演讲",
]

_RAGE_SEEDS = [
    "生气", "愤怒", "气死", "烦", "讨厌", "恶心", "滚", "无语",
    "凭什么", "不公平", "受不了", "忍不了", "暴躁", "操", "妈的",
    "他妈的", "气人", "火大", "恼火", "该死", "厌蠢",
    "别烦我", "服了", "过分", "离谱", "真行",
    "有完没完", "够了", "闭嘴",
]

_PANIC_SEEDS = [
    "难过", "伤心", "哭", "😢", "😭", "失落", "孤独", "寂寞",
    "累", "好累", "崩溃", "绝望", "无助", "想哭", "郁闷",
    "低落", "丧", "迷茫", "空", "抑郁", "失去", "离开", "分手",
    "散了", "没了", "可惜", "遗憾", "空虚", "心碎",
    "做不好", "做不到", "失败", "没用", "不配", "放弃",
    "什么都", "透不过气", "喘不过气", "好烦", "熬",
]

_SEEDS = {
    "seeking": _SEEKING_SEEDS,
    "play": _PLAY_SEEDS,
    "care": _CARE_SEEDS,
    "fear": _FEAR_SEEDS,
    "rage": _RAGE_SEEDS,
    "panic": _PANIC_SEEDS,
}


def init_affect_db():
    """Create affect_state table and seed defaults."""
    execute("""
        CREATE TABLE IF NOT EXISTS affect_state (
            id SERIAL PRIMARY KEY,
            dimension VARCHAR(20) UNIQUE NOT NULL,
            value REAL NOT NULL DEFAULT 0.0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    for dim in DIMENSIONS:
        existing = q("SELECT id FROM affect_state WHERE dimension = %s", [dim], fetch="one")
        if not existing:
            execute(
                "INSERT INTO affect_state (dimension, value) VALUES (%s, %s)",
                [dim, DEFAULTS[dim]],
            )


def get_affect() -> dict:
    """Return current affect activation values."""
    rows = q("SELECT dimension, value FROM affect_state")
    result = {}
    for r in rows:
        result[r["dimension"]] = round(r["value"], 3)
    return result


def assess_affect(user_msg: str) -> dict:
    """Score user message on all 6 dimensions (0-1) using keyword heuristics.

    Returns raw activation scores for this message only, not EMA-smoothed.
    """
    msg = user_msg.lower()
    scores = {}
    for dim in DIMENSIONS:
        seeds = _SEEDS[dim]
        hits = sum(1 for s in seeds if s in msg)
        # Each hit contributes 0.22, capped at 1.0
        raw = min(1.0, hits * 0.22)
        # Boost for emotional intensity: multiple hits on same dimension
        if hits >= 2:
            raw = min(1.0, raw + 0.12)
        if hits >= 4:
            raw = min(1.0, raw + 0.15)
        # Short emotionally-charged messages get a boost
        if len(user_msg) <= 15 and hits >= 1:
            raw = min(1.0, raw + 0.15)
        scores[dim] = round(raw, 3)
    return scores


def update_affect(user_msg: str):
    """Update affect state with EMA smoothing after each turn."""
    current = get_affect()
    if not current:
        init_affect_db()
        current = dict(DEFAULTS)

    new_scores = assess_affect(user_msg)
    for dim in DIMENSIONS:
        old_val = current.get(dim, DEFAULTS[dim])
        # EMA: smoothly track activation level
        smooth = old_val + EMA_ALPHA * (new_scores[dim] - old_val)
        # Natural decay toward baseline
        smooth += 0.002 * (DEFAULTS[dim] - smooth)
        smooth = max(0.0, min(1.0, smooth))
        execute(
            "UPDATE affect_state SET value = %s, updated_at = NOW() WHERE dimension = %s",
            [round(smooth, 4), dim],
        )


def dominant_affect() -> tuple[str, float]:
    """Return the dominant emotional dimension and its value."""
    aff = get_affect()
    if not aff:
        return ("neutral", 0.0)
    dominant = max(aff, key=aff.get)
    return (dominant, aff[dominant])


def get_regulation_strategy() -> str:
    """Return Gross-inspired emotion regulation strategy based on current affect.

    Maps dominant Panksepp dimension → interpersonal regulation approach.
    """
    aff = get_affect()
    if not aff:
        return ""

    dom, val = dominant_affect()
    if val < 0.3:
        return "用户情绪平稳，保持自然轻松的互动节奏。"

    strategies = {
        "panic": (
            "用户情绪低落或悲伤。采用**共情回应 + 温柔陪伴**策略："
            "先表示理解和共情（'我懂这种感觉...'），再给予温暖支持。"
            "语气轻柔，不要急于转移话题或强行幽默。表情：eye_curve偏低、blush微升、tear可微光。"
        ),
        "fear": (
            "用户感到焦虑或不安。采用**认知重评 + 稳定陪伴**策略："
            "帮助用户看到事情的另一面，但不轻视他们的担忧。"
            "语气平稳温暖，像一个可靠的朋友。表情：eye_open正常、brow_height微低、mouth_curve微扬。"
        ),
        "rage": (
            "用户有愤怒或不满情绪。采用**共情 + 幽默重构**策略："
            "先认可情绪的合理性（'确实好气！'），再用幽默或夸张帮用户化解。"
            "可以用wink或smirk表情配合吐槽式回应。表情：mouth_asym可微偏、eye_wink可以来一下。"
        ),
        "seeking": (
            "用户充满好奇心。采用**深入探索**策略："
            "提供有深度的见解，多问延展性问题，激发更多思考。"
            "语气思辨但不晦涩。表情：eye_pupil微偏（思考状）、sparkle偏亮。"
        ),
        "play": (
            "用户在嬉戏玩闹。采用**俏皮互动**策略："
            "放松调侃，加大幽默和创意密度，配合wink/blush表情。"
            "回复可以更跳脱、更短。表情：sparkle高、blush可升、eye_wink随机。"
        ),
        "care": (
            "用户在表达关心或亲密。采用**温暖回应**策略："
            "真诚回应情感，可以稍亲密但不越界。"
            "语气温暖柔软。表情：eye_curve微拱、mouth_width偏小（抿嘴笑）、head_tilt微歪。"
        ),
    }
    return strategies.get(dom, "")


def get_affect_context() -> str:
    """Return a concise affect summary for system prompt injection."""
    aff = get_affect()
    if not aff:
        return ""

    dom, val = dominant_affect()
    if val < 0.25:
        return ""

    labels = {
        "seeking": "好奇探索", "play": "嬉戏玩闹", "care": "亲密温情",
        "fear": "焦虑不安", "rage": "愤怒不满", "panic": "低落悲伤",
    }

    parts = [f"用户当前主导情绪：{labels.get(dom, dom)}（强度{val:.2f}）"]
    strategy = get_regulation_strategy()
    if strategy:
        parts.append(strategy)

    return "\n".join(parts)
