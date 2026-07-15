"""Dual-system cognition — Kahneman's System 1 (fast) + System 2 (slow).

System 1: fast, intuitive, pattern-matching — existing mode/emotion/temperature pipeline.
System 2: slow, deliberative, analytical — deep thinking with contradiction detection.

GATE (门控逻辑) evaluates multiple signals to decide which system(s) to engage.
System 2 insights feed back into System 1 via periodic consolidation.
"""

import json
import logging
import threading
from datetime import datetime, timezone

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

_DEEP_MARKERS = [
    "为什么", "怎么看", "如何看待", "如何理解", "你觉得呢",
    "你怎么想", "意味着什么", "本质", "意义", "存在",
    "意识", "自由意志", "哲学", "人生观", "世界观",
    "人生的意义", "活着的意义", "什么是爱", "幸福是什么",
    "怎么才能", "如何变得", "我该怎么办",
]

_CONTRADICT_PROMPT = """检测以下内容是否存在矛盾：

AI已知信息（知识图谱）：
{kg_context}

用户当前消息：
{user_msg}

判断用户当前说法是否与已知信息矛盾。返回JSON：
{{"contradiction": true/false, "description": "矛盾描述", "confidence": 0.0-1.0}}

只输出JSON，不要其他内容。"""

_IMPACT_PROMPT = """评估以下AI回复对用户关系的长期影响：

用户消息：{user_msg}
AI回复：{avatar_reply}

从以下维度评估（各0-1分）：
- trust_impact: 对信任的影响
- warmth_impact: 对温暖度的影响
- engagement_impact: 对参与度的影响
- risk_level: 风险等级（0=无风险, 1=高风险）

返回JSON：
{{"trust_impact": 0.1, "warmth_impact": 0.2, "engagement_impact": 0.15, "risk_level": 0.05, "assessment": "简短评估"}}

只输出JSON，不要其他内容。"""


def gate_decision(msg: str, affect: dict | None = None,
                 salience: dict | None = None,
                 prediction_error: float = 0.0,
                 idle_minutes: float = 0.0) -> str:
    """Multi-factor gate: decide whether to engage System 2.

    Returns "system1", "system2", or "both".

    System 2 triggers (any one suffices for "both", 3+ for full "system2"):
    """
    triggers = []
    reasons = []

    if len(msg) > 50:
        triggers.append("length")
        reasons.append("消息较长")

    if any(m in msg for m in _DEEP_MARKERS):
        triggers.append("deep_markers")
        reasons.append("包含深度话题标记")

    if salience and salience.get("conflict", 0) > 0.3:
        triggers.append("conflict")
        reasons.append(f"认知冲突({salience['conflict']:.2f})")

    if affect:
        arousal = affect.get("arousal", 0)
        valence = affect.get("valence", 0)
        # Use seeking/rage/panic dimensions as proxy for arousal
        high_arousal = (
            affect.get("seeking", 0) > 0.6 or
            affect.get("rage", 0) > 0.3 or
            affect.get("panic", 0) > 0.4
        )
        negative_valence = valence < -0.2
        if high_arousal and negative_valence:
            triggers.append("high_arousal_negative")
            reasons.append("高唤醒+负面情绪")

    if idle_minutes > 30:
        triggers.append("long_idle")
        reasons.append(f"空闲{idle_minutes:.0f}分钟后回归")

    if prediction_error > 0.5:
        triggers.append("prediction_error")
        reasons.append(f"预测误差({prediction_error:.2f})")

    if not triggers:
        return "system1"

    if len(triggers) >= 3:
        logger.info("System 2 gate → system2 (%d triggers: %s)",
                     len(triggers), ", ".join(reasons))
        return "system2"

    logger.info("System 2 gate → both (%d triggers: %s)",
                 len(triggers), ", ".join(reasons))
    return "both"


def _get_llm():
    from app.utils import get_llm
    return get_llm()


def detect_contradictions(user_msg: str) -> dict | None:
    """Check user message against knowledge graph for contradictions.

    Returns {"contradiction": bool, "description": str, "confidence": float} or None.
    """
    try:
        from services.memory.knowledge_graph import get_knowledge_graph_context
        kg_ctx = get_knowledge_graph_context()
        if not kg_ctx:
            return None

        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _CONTRADICT_PROMPT.format(
                    kg_context=kg_ctx[:800],
                    user_msg=user_msg[:200],
                )},
                {"role": "user", "content": "检测矛盾。"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=200,
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            "contradiction": bool(data.get("contradiction", False)),
            "description": str(data.get("description", "")),
            "confidence": float(data.get("confidence", 0)),
        }
    except Exception:
        logger.warning("Contradiction detection failed", exc_info=True)
        return None


def assess_impact(user_msg: str, avatar_reply: str) -> dict | None:
    """Assess the long-term relationship impact of a reply.

    Returns impact scores for trust, warmth, engagement, risk.
    """
    if len(user_msg) < 10 or len(avatar_reply) < 10:
        return None
    try:
        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _IMPACT_PROMPT.format(
                    user_msg=user_msg[:200],
                    avatar_reply=avatar_reply[:300],
                )},
                {"role": "user", "content": "评估影响。"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=200,
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            "trust_impact": float(data.get("trust_impact", 0)),
            "warmth_impact": float(data.get("warmth_impact", 0)),
            "engagement_impact": float(data.get("engagement_impact", 0)),
            "risk_level": float(data.get("risk_level", 0)),
            "assessment": str(data.get("assessment", "")),
        }
    except Exception:
        logger.warning("Impact assessment failed", exc_info=True)
        return None


def store_insight(insight: str, source_message: str = "",
                  category: str = "general"):
    """Store a System 2 insight for later integration into System 1."""
    try:
        execute(
            "INSERT INTO system2_insights (insight, source_message, category) "
            "VALUES (%s, %s, %s)",
            [insight[:500], source_message[:200], category[:50]],
        )
    except Exception:
        logger.warning("Store insight failed", exc_info=True)


def system2_consolidation():
    """Periodic integration: apply unapplied System 2 insights to System 1.

    Called from consciousness_loop every ~30 minutes. Reads recent insights
    and adjusts System 1 parameters (emotion cache, state machine thresholds, etc.).
    """
    try:
        rows = q(
            "SELECT id, insight, category FROM system2_insights "
            "WHERE applied_to_system1 = FALSE AND created_at > NOW() - INTERVAL '7 days' "
            "ORDER BY id ASC LIMIT 10"
        )
        if not rows:
            return

        for r in rows:
            insight = r["insight"][:200]
            category = r["category"]
            # Store high-quality patterns with s2_ prefix in emotion cache
            if category in ("response_pattern", "emotion_strategy", "mode_advice"):
                execute(
                    "INSERT INTO emotion_cache (label, reply) VALUES (%s, %s) "
                    "ON CONFLICT (label) DO UPDATE SET reply = EXCLUDED.reply, "
                    "updated_at = NOW()",
                    [f"s2_{r['id']}", insight],
                )

            execute(
                "UPDATE system2_insights SET applied_to_system1 = TRUE WHERE id = %s",
                [r["id"]],
            )

        logger.info("System 2 consolidation: %d insights integrated", len(rows))
    except Exception:
        logger.warning("System 2 consolidation failed", exc_info=True)
