"""Predictive Agent — anticipates user needs, emotions, and topics.

Upgrades the simple "predict next sentence" in prediction.py to a
three-dimensional predictive model:

  NEED    — what the user wants (倾诉/求助/闲聊/答疑/陪伴)
  EMOTION — likely emotional state based on time + history patterns
  TOPIC   — continuing recent conversation threads

Prediction results feed into memory preloading and system prompt context.
Feedback learning stores prediction-vs-actual in prediction_history table.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

from app.db import q, execute
from app.utils import get_llm_model

logger = logging.getLogger("emoji-chat")

_NEED_TYPES = ["倾诉", "求助", "闲聊", "答疑", "陪伴"]
_EMOTION_TYPES = ["开心", "难过", "焦虑", "平静", "兴奋", "疲惫", "愤怒", "困惑"]

_last_prediction = None
_pred_lock = threading.Lock()

_ANALYZE_PROMPT = """分析以下对话上下文，预测用户接下来最可能的：
1. 需求（倾诉/求助/闲聊/答疑/陪伴）
2. 情绪（开心/难过/焦虑/平静/兴奋/疲惫/愤怒/困惑）
3. 话题延续（一句话概括用户可能在聊什么）

输出JSON：
{{"need": "闲聊", "emotion": "平静", "topic": "周末计划", "confidence": 0.7, "reason": "简短理由"}}

只输出JSON，不要其他内容。"""


def _get_llm():
    from app.utils import get_llm, get_llm_model
    return get_llm()


def _get_time_context() -> str:
    """Describe the current time pattern for prediction."""
    hour = datetime.now().hour
    weekday = datetime.now().weekday()
    if 6 <= hour < 9:
        base = "早晨时段，用户可能刚起床"
    elif 9 <= hour < 12:
        base = "上午工作/学习时段"
    elif 12 <= hour < 14:
        base = "午休时段"
    elif 14 <= hour < 18:
        base = "下午时段"
    elif 18 <= hour < 21:
        base = "晚间放松时段"
    elif 21 <= hour < 24:
        base = "深夜，用户可能比较感性"
    else:
        base = "凌晨，用户可能失眠或熬夜"
    if weekday >= 5:
        base += "，周末休息日"
    return base


def _get_recent_history(n: int = 6) -> str:
    """Get recent conversation turns for prediction context."""
    rows = q(
        "SELECT user_msg, avatar_reply FROM chat_history ORDER BY id DESC LIMIT %s",
        [n],
    )
    if not rows:
        return ""
    lines = []
    for r in reversed(rows):
        lines.append(f"用户：{r['user_msg'][:100]}")
        if r["avatar_reply"]:
            lines.append(f"AI：{r['avatar_reply'][:100]}")
    return "\n".join(lines)


def pre_dialogue_analyze() -> dict | None:
    """Analyze time patterns and recent history to predict user state.

    Called at the start of each chat turn. Returns predicted dimensions
    that feed into memory preloading and context building.

    Returns None if insufficient history.
    """
    history = _get_recent_history(6)
    if not history:
        return None

    time_ctx = _get_time_context()

    try:
        client = _get_llm()
        if client is None:
            return None
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _ANALYZE_PROMPT},
                {"role": "user", "content": f"时间背景：{time_ctx}\n\n最近对话：\n{history}\n\n请预测用户接下来最可能的需求、情绪和话题。"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw)
        prediction = {
            "need": str(data.get("need", "闲聊")),
            "emotion": str(data.get("emotion", "平静")),
            "topic": str(data.get("topic", "")),
            "confidence": float(data.get("confidence", 0.5)),
            "reason": str(data.get("reason", "")),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        global _last_prediction
        with _pred_lock:
            _last_prediction = prediction
        logger.info("Prediction: need=%s emotion=%s topic=%s confidence=%.2f",
                     prediction["need"], prediction["emotion"],
                     prediction["topic"][:30], prediction["confidence"])
        return prediction
    except Exception:
        logger.warning("Pre-dialogue analysis failed", exc_info=True)
        return None


def preload_memories(need: str, topic: str) -> str:
    """Preload relevant memories based on predicted need and topic.

    Returns memory context string for injection into system prompt.
    """
    query_parts = []
    if need and need != "闲聊":
        query_parts.append(need)
    if topic:
        query_parts.append(topic)
    if not query_parts:
        return ""

    query = " ".join(query_parts)
    try:
        from services.memory.search import search_similar
        results = search_similar(query, limit=3, use_rerank=False)
        if not results:
            return ""

        lines = ["## 预测相关记忆（预加载）："]
        for r in results:
            lines.append(f"- 用户曾说过：「{r['user_msg'][:80]}」→ 你回复：「{r['avatar_reply'][:60]}」")
        return "\n".join(lines)
    except Exception:
        logger.warning("Memory preload failed", exc_info=True)
        return ""


def feedback(actual_need: str = "", actual_emotion: str = "",
             actual_topic: str = ""):
    """Store prediction-vs-actual for learning.

    Compares the most recent prediction against actual outcomes and
    saves to prediction_history table.
    """
    global _last_prediction
    with _pred_lock:
        pred = _last_prediction
        _last_prediction = None

    if not pred:
        return

    # Count how many dimensions we have actual values for
    matches = 0
    provided = 0
    if actual_need:
        provided += 1
        if pred["need"] == actual_need:
            matches += 1
    if actual_emotion:
        provided += 1
        if pred["emotion"] == actual_emotion:
            matches += 1
    if actual_topic:
        provided += 1
        if pred["topic"] == actual_topic:
            matches += 1

    if provided == 0:
        return  # nothing to compare — don't write bogus data

    error = 1.0 - (matches / provided)

    try:
        execute(
            "INSERT INTO prediction_history "
            "(predicted_need, predicted_emotion, predicted_topic, "
            "actual_need, actual_emotion, actual_topic, prediction_error) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [pred["need"], pred["emotion"], pred["topic"],
             actual_need or None, actual_emotion or None, actual_topic or None,
             round(error, 4)],
        )
    except Exception:
        logger.warning("Feedback storage failed", exc_info=True)


def get_prediction_context() -> str:
    """Build prediction context for system prompt injection.

    Returns a hint about what the user likely needs right now,
    so the AI can proactively adjust its approach.
    """
    global _last_prediction
    with _pred_lock:
        pred = _last_prediction

    if not pred:
        return ""

    confidence = pred.get("confidence", 0)
    if confidence < 0.4:
        return ""

    need_hints = {
        "倾诉": "用户可能需要倾诉，请多倾听、共情，少给建议",
        "求助": "用户可能需要帮助，请提供实用、清晰的建议",
        "闲聊": "用户想轻松聊天，保持轻快、幽默的风格",
        "答疑": "用户想了解某个问题，请给出有深度的解答",
        "陪伴": "用户可能感到孤独，请给予温暖陪伴感",
    }
    hint = need_hints.get(pred["need"], "")

    parts = ["## 预测引擎提示："]
    if hint:
        parts.append(f"- {hint}")
    if pred.get("emotion"):
        parts.append(f"- 预测用户情绪：{pred['emotion']}")
    if pred.get("topic"):
        parts.append(f"- 预测话题方向：{pred['topic'][:60]}")
    parts.append(f"- 置信度：{confidence:.0%}")

    return "\n".join(parts)


def offline_analysis():
    """Periodic analysis: compute prediction accuracy trends.

    Called every ~5 minutes from background scheduler. Analyzes recent
    prediction_history to detect patterns in prediction errors.
    """
    try:
        row = q(
            "SELECT AVG(prediction_error) AS avg_error, COUNT(*) AS cnt "
            "FROM prediction_history "
            "WHERE created_at > NOW() - INTERVAL '24 hours'",
            fetch="one",
        )
        if row and row["cnt"] and row["cnt"] > 5:
            avg = float(row["avg_error"])
            logger.info("Prediction accuracy (24h): avg_error=%.2f, n=%d", avg, row["cnt"])
    except Exception:
        logger.warning("Offline prediction analysis failed", exc_info=True)
