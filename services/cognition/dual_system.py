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
from app.utils import get_llm_model

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

从以下维度评估：
- trust_impact: 对信任的影响（-0.1到0.1，负=降低信任，正=增强信任）
- warmth_impact: 对温暖度的影响（-0.1到0.1）
- engagement_impact: 对参与度的影响（-0.1到0.1）
- risk_level: 风险等级（0=无风险，1=高风险）

返回JSON：
{{"trust_impact": 0.0, "warmth_impact": 0.0, "engagement_impact": 0.0, "risk_level": 0.0, "assessment": "简短评估"}}

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
    from app.utils import get_llm, get_llm_model
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
        if client is None:
            return None
        resp = client.chat.completions.create(
            model=get_llm_model(),
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
        if client is None:
            return None
        resp = client.chat.completions.create(
            model=get_llm_model(),
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


# ── Self-Evaluation Loop ─────────────────────────────────────────
# Three-layer quality assurance for AI replies:
# Layer 1: Real-time per-reply assessment (background, non-blocking)
# Layer 2: Deferred correction injection (next turn's system prompt)
# Layer 3: Periodic deep audit (every 50 turns, LLM trend analysis)

_DEEP_AUDIT_EVERY = 50
_AUDIT_LOCK = threading.Lock()
_last_audit_count = 0

_SELF_EVAL_CORRECT_PROMPTS: dict[str, str] = {
    "risk_high": "\n[自评提醒] 你上一条回复的风险等级较高，请注意表达的分寸和边界。",
    "low_trust": "\n[自评提醒] 你上一条回复的信任影响偏弱，在接下来的回复中多一些真诚和一致性。",
    "contradiction": "\n[自评提醒] 你上一条回复中的表述与已知信息存在潜在矛盾，请注意核实。",
}
_OVERALL_THRESHOLD = 0.45


def self_evaluate(user_msg: str, avatar_reply: str, turn_id: int | None = None) -> None:
    """Layer 1: Real-time self-evaluation after each reply.

    Reuses existing assess_impact() and detect_contradictions() for
    relationship impact and knowledge-graph consistency checks.
    Runs in background thread — never blocks the user.
    """
    try:
        impact = assess_impact(user_msg, avatar_reply)
        contra = detect_contradictions(user_msg)

        trust_imp = impact["trust_impact"] if impact else 0
        warmth_imp = impact["warmth_impact"] if impact else 0
        engage_imp = impact["engagement_impact"] if impact else 0
        risk_lvl = impact["risk_level"] if impact else 0
        assessment = impact.get("assessment", "") if impact else ""

        has_contra = bool(contra and contra.get("contradiction"))
        contra_desc = contra.get("description", "") if contra else ""
        contra_conf = contra.get("confidence", 0) if contra else 0

        # Composite overall score: normalize -0.1~0.1 impacts → 0~1
        trust_score = (trust_imp + 0.1) / 0.2
        warmth_score = (warmth_imp + 0.1) / 0.2
        engage_score = (engage_imp + 0.1) / 0.2
        risk_score = 1.0 - risk_lvl
        overall = round(
            0.3 * trust_score + 0.25 * warmth_score
            + 0.25 * engage_score + 0.2 * risk_score, 4
        )
        overall = max(0.0, min(1.0, overall))

        if risk_lvl > 0.7:
            logger.warning("High risk reply detected (risk=%.2f, turn=%s)", risk_lvl, turn_id)

        execute(
            "INSERT INTO self_eval_log (turn_id, user_msg, avatar_reply, "
            "trust_impact, warmth_impact, engagement_impact, risk_level, "
            "impact_assessment, has_contradiction, contradiction_desc, "
            "contradiction_confidence, overall_score) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [turn_id, user_msg[:500], avatar_reply[:500],
             round(trust_imp, 4), round(warmth_imp, 4), round(engage_imp, 4),
             round(risk_lvl, 4), assessment[:300],
             has_contra, contra_desc[:300], round(contra_conf, 4), overall],
        )
    except Exception:
        logger.warning("Self-evaluation failed", exc_info=True)


def get_self_eval_correction() -> str:
    """Layer 2: Read latest self-eval and return correction prompt if needed.

    Follows the same deferred-correction pattern as get_drift_correction().
    Called during _build_context() — only a single DB read, no LLM.
    """
    try:
        row = q(
            "SELECT overall_score, risk_level, has_contradiction, trust_impact "
            "FROM self_eval_log ORDER BY id DESC LIMIT 1",
            fetch="one",
        )
        if not row:
            return ""

        parts = []
        risk_high_added = False
        if row["risk_level"] is not None and row["risk_level"] > 0.7:
            parts.append(_SELF_EVAL_CORRECT_PROMPTS["risk_high"])
            risk_high_added = True
        if row["overall_score"] is not None and row["overall_score"] < _OVERALL_THRESHOLD:
            if not risk_high_added:
                parts.append("你上一条回复的质量评分偏低，请在接下来的回复中稍微调整表达方式。")
        if row["has_contradiction"]:
            parts.append(_SELF_EVAL_CORRECT_PROMPTS["contradiction"])
        if (row["trust_impact"] is not None and row["trust_impact"] < -0.03
                and row["risk_level"] is not None and row["risk_level"] <= 0.7):
            parts.append(_SELF_EVAL_CORRECT_PROMPTS["low_trust"])

        return "\n".join(parts) if parts else ""
    except Exception:
        logger.warning("Self-eval correction lookup failed", exc_info=True)
        return ""


def deep_self_audit() -> None:
    """Layer 3: Periodic deep audit of reply quality trends.

    Reads recent self_eval_log entries, calls LLM for trend analysis,
    and stores insights for later System 1 consolidation.
    """
    try:
        rows = q(
            "SELECT overall_score, risk_level, has_contradiction "
            "FROM self_eval_log ORDER BY id DESC LIMIT 30"
        )
        if len(rows) < 10:
            return

        scores = [r["overall_score"] for r in rows if r["overall_score"] is not None]
        if not scores:
            return

        avg_score = sum(scores) / len(scores)
        high_risk = sum(1 for r in rows if r["risk_level"] is not None and r["risk_level"] > 0.5)
        contradictions = sum(1 for r in rows if r["has_contradiction"])

        if avg_score >= 0.55 and high_risk <= 3 and contradictions <= 2:
            return  # Quality is fine, skip LLM call

        summary = (
            f"最近{len(rows)}轮自评: 均分{avg_score:.2f}, "
            f"高风险{high_risk}次, 矛盾{contradictions}次"
        )

        client = _get_llm()
        if client is None:
            return

        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": (
                    "你是AI自我反思系统。分析回复质量趋势并给出改进建议。返回JSON: "
                    '{"trend": "up/stable/down", "key_issues": "主要问题", '
                    '"suggestion": "改进建议", "adjust_amplitude": true/false, '
                    '"amplitude_delta": -0.1~0.1}'
                )},
                {"role": "user", "content": summary},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=200,
        )
        data = json.loads(resp.choices[0].message.content)
        trend = data.get("trend", "stable")
        suggestion = data.get("suggestion", "")

        if trend == "down" and suggestion:
            store_insight(
                f"[自评审计] 质量趋势下降: {suggestion}",
                source_message=summary,
                category="self_eval_audit",
            )
            logger.info("Deep self-audit: quality trending down, insight stored. %s", suggestion)

        if data.get("adjust_amplitude"):
            delta = float(data.get("amplitude_delta", 0))
            if abs(delta) > 0.02:
                execute(
                    "UPDATE affinity SET value = LEAST(1.5, GREATEST(0.5, value + %s)), "
                    "updated_at = NOW() WHERE dimension = 'expression_amplitude'",
                    [round(delta, 3)],
                )
    except Exception:
        logger.warning("Deep self-audit failed", exc_info=True)


def maybe_deep_audit():
    """Thread-safe wrapper: run deep_self_audit every _DEEP_AUDIT_EVERY evaluations.

    Uses non-blocking lock + count check, same pattern as maybe_guard().
    """
    global _last_audit_count
    if not _AUDIT_LOCK.acquire(blocking=False):
        return
    try:
        row = q("SELECT COUNT(*) AS cnt FROM self_eval_log", fetch="one")
        if not row:
            return
        cnt = row["cnt"]
        if cnt - _last_audit_count < _DEEP_AUDIT_EVERY:
            return
        deep_self_audit()
        _last_audit_count = cnt
    except Exception:
        logger.warning("Deep audit check failed", exc_info=True)
    finally:
        _AUDIT_LOCK.release()
