"""Multi-turn conversation goal tracking.

Tracks what the user is trying to accomplish across multiple conversation
turns (venting, advice-seeking, sharing, debating, or just chatting).

Pure rules + affect analysis — zero extra LLM calls. Updates each turn
from _post_reply_pipeline, injects context via _build_context.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

from app.config import MEMORY_DIR, atomic_write

logger = logging.getLogger("emoji-chat")

GOAL_PATH = os.path.join(MEMORY_DIR, "conversation_goal.json")

_lock = threading.Lock()

# Goal types and their keyword signals
_GOAL_SIGNALS = {
    "venting": [
        "烦", "累", "难受", "崩溃", "撑不住", "无语", "气死", "好气",
        "太惨", "好惨", "心态", "委屈", "压抑", "焦虑", "压力",
        "不开心", "低落", "郁闷", "想哭", "难过", "伤心", "绝望",
        "好累啊", "心累", "不想", "好难", "太难了",
    ],
    "advice_seeking": [
        "怎么办", "帮我想想", "你觉得", "建议", "怎么选", "该不该",
        "能不能", "怎么处理", "怎么弄", "怎么解决", "怎么面对",
        "怎么应对", "有什么办法", "怎么劝", "有什么建议",
    ],
    "sharing": [
        "今天", "刚刚", "昨天", "最近", "分享一下", "跟你说",
        "告诉你", "哈哈哈", "笑死", "好玩", "有趣", "开心",
        "好消息", "成功了", "拿到了", "终于",
    ],
    "debate": [
        "你觉得呢", "怎么看", "为什么", "如何看待", "是不是",
        "难道", "对不对", "会不会是", "有没有可能",
    ],
}


def _classify_goal(msg: str, affect: dict | None) -> str:
    """Classify the current turn's conversational goal."""
    # Strong negative affect → venting takes priority
    if affect:
        neg = max(affect.get("panic", 0), affect.get("fear", 0), affect.get("rage", 0))
        if neg > 0.3:
            # Check if it's venting or advice-seeking with distress
            if any(kw in msg for kw in _GOAL_SIGNALS["advice_seeking"]):
                return "advice_seeking"
            return "venting"

    # Question-heavy + debate markers → debate
    debate_count = sum(1 for kw in _GOAL_SIGNALS["debate"] if kw in msg)
    if debate_count >= 2 or (debate_count >= 1 and len(msg) > 60):
        return "debate"

    # Explicit advice-seeking
    if any(kw in msg for kw in _GOAL_SIGNALS["advice_seeking"]):
        return "advice_seeking"

    # Sharing (positive or neutral new information)
    if any(kw in msg for kw in _GOAL_SIGNALS["sharing"]):
        return "sharing"

    # Light venting (without strong affect)
    if any(kw in msg for kw in _GOAL_SIGNALS["venting"]):
        return "venting"

    return "small_talk"


def _load_state() -> dict:
    if os.path.exists(GOAL_PATH):
        try:
            with open(GOAL_PATH) as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to load conversation goal", exc_info=True)
    return {
        "goal": "small_talk",
        "turns_in_goal": 0,
        "affect_trend": "stable",
        "prev_neg_affect": 0.0,
        "start_turn": 0,
        "updated_at": "",
    }


def _save_state(state: dict):
    try:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_write(GOAL_PATH, json.dumps(state, ensure_ascii=False, indent=2))
    except Exception:
        logger.warning("Failed to save conversation goal", exc_info=True)


def update_conversation_goal(msg: str, affect: dict | None = None):
    """Classify the current turn and update goal tracking state.

    Called from _post_reply_pipeline every turn. Lightweight — no LLM.
    """
    with _lock:
        state = _load_state()
        current_goal = _classify_goal(msg, affect)

        # Compute current negative affect for trend tracking
        neg = 0.0
        if affect:
            neg = max(affect.get("panic", 0), affect.get("fear", 0), affect.get("rage", 0))

        if current_goal == state.get("goal"):
            # Same goal continues
            state["turns_in_goal"] = state.get("turns_in_goal", 0) + 1
        else:
            # Goal changed — reset counter
            state["goal"] = current_goal
            state["turns_in_goal"] = 1

        # Track affect trend (EMA of negative affect, alpha=0.3)
        prev = state.get("prev_neg_affect", 0.0)
        smoothed = prev * 0.7 + neg * 0.3
        if smoothed > prev + 0.05:
            state["affect_trend"] = "worsening"
        elif smoothed < prev - 0.05:
            state["affect_trend"] = "improving"
        else:
            state["affect_trend"] = "stable"
        state["prev_neg_affect"] = round(smoothed, 4)

        _save_state(state)


def get_goal_context() -> str:
    """Generate a natural-language hint about the current conversation goal.

    Returns empty string for small_talk or if fewer than 2 turns in goal.
    """
    state = _load_state()
    goal = state.get("goal", "small_talk")
    turns = state.get("turns_in_goal", 0)
    trend = state.get("affect_trend", "stable")

    if goal == "small_talk" or turns < 2:
        return ""

    hints = {
        "venting": (
            "当前对话上下文：用户正在倾诉烦恼，已经持续了{turns}轮。"
            "你心里记着这件事，但不需要每轮都提——让对话自然流动。"
            "如果情绪有好转的迹象，可以温和地引导到轻松的方向。"
        ),
        "advice_seeking": (
            "当前对话上下文：用户似乎在寻求建议或帮助，持续了{turns}轮。"
            "先听听用户自己的想法，再给出你的看法。不要一上来就给建议。"
        ),
        "sharing": (
            "当前对话上下文：用户在分享生活中的事情，持续了{turns}轮。"
            "表现出真实的兴趣和好奇，用开放式问题引导更多细节。"
        ),
        "debate": (
            "当前对话上下文：用户在和你探讨/辩论一个话题，持续了{turns}轮。"
            "保持思辨但不较劲——你是朋友，不是辩论对手。可以说'也有可能...'来保持开放。"
        ),
    }

    hint = hints.get(goal, "")
    if not hint:
        return ""

    trend_hint = ""
    if goal in ("venting", "advice_seeking"):
        if trend == "improving":
            trend_hint = "用户的情绪似乎在好转。"
        elif trend == "worsening":
            trend_hint = "用户的情绪似乎还没有缓解，继续倾听为主。"

    return hint.format(turns=turns) + trend_hint
