"""干预效果追踪 — 零 LLM 成本.

追踪每次治疗干预的效果:
- 干预前捕获 affect 六维快照
- 干预后(用户下一轮回复前)捕获 affect 快照
- 计算六维 delta 和综合指标 (distress_reduction / valence_improvement)
- 持久化到 intervention_outcomes 表

模式: 后台任务, 每条有治疗意图的消息后触发.
"""

import json
import logging
from datetime import datetime, timezone

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

# ── 干预类型映射 ──
_INTENT_TO_TYPE = {
    "cbt_needed": "cbt",
    "mindfulness": "mindfulness",
    "venting": "venting",
    "crisis": "crisis",
}


def capture_affect_snapshot() -> dict:
    """读取当前六维 affect 快照."""
    from services.emotion.affect import get_affect
    return get_affect() or {}


def _compute_delta(before: dict, after: dict) -> dict:
    """计算六维 affect delta: after - before."""
    delta = {}
    for dim in ("seeking", "play", "care", "fear", "rage", "panic"):
        b = float(before.get(dim, 0))
        a = float(after.get(dim, 0))
        delta[dim] = round(a - b, 4)
    return delta


def _compute_indicators(before: dict, after: dict) -> tuple[float, float]:
    """计算 distress_reduction 和 valence_improvement.

    distress = panic + fear
    valence = (seeking + play + care) - (panic + fear + rage)
    """
    b_panic = float(before.get("panic", 0))
    b_fear = float(before.get("fear", 0))
    b_seeking = float(before.get("seeking", 0))
    b_play = float(before.get("play", 0))
    b_care = float(before.get("care", 0))
    b_rage = float(before.get("rage", 0))

    a_panic = float(after.get("panic", 0))
    a_fear = float(after.get("fear", 0))
    a_seeking = float(after.get("seeking", 0))
    a_play = float(after.get("play", 0))
    a_care = float(after.get("care", 0))
    a_rage = float(after.get("rage", 0))

    distress_before = b_panic + b_fear
    distress_after = a_panic + a_fear
    distress_reduction = round(distress_before - distress_after, 4)

    valence_before = (b_seeking + b_play + b_care) - (b_panic + b_fear + b_rage)
    valence_after = (a_seeking + a_play + a_care) - (a_panic + a_fear + a_rage)
    valence_improvement = round(valence_after - valence_before, 4)

    return distress_reduction, valence_improvement


def log_intervention_outcome(
    turn_id: int | None,
    intervention_type: str,
    affect_before: dict,
    user_msg: str = "",
    session_id: str = "default",
) -> int | None:
    """干预后调用: 读取当前 affect, 计算 delta, 写入 DB.

    参数:
        turn_id: chat_history.id (干预发生的轮次)
        intervention_type: therapy_intent 的 intent 值
        affect_before: 干预前的六维快照
        user_msg: 触发干预的用户消息
        session_id: 会话标识
    """
    if not affect_before:
        return None

    affect_after = capture_affect_snapshot()
    if not affect_after:
        return None

    intervention_label = _INTENT_TO_TYPE.get(intervention_type, intervention_type)
    delta = _compute_delta(affect_before, affect_after)
    distress_reduction, valence_improvement = _compute_indicators(affect_before, affect_after)

    try:
        row = q(
            """INSERT INTO intervention_outcomes
               (turn_id, intervention_type, trigger_intent,
                affect_before, affect_after, affect_delta,
                distress_reduction, valence_improvement,
                user_msg, session_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            [
                turn_id,
                intervention_label,
                intervention_type,
                json.dumps(affect_before, ensure_ascii=False),
                json.dumps(affect_after, ensure_ascii=False),
                json.dumps(delta, ensure_ascii=False),
                distress_reduction,
                valence_improvement,
                user_msg[:500],
                session_id,
            ],
            fetch="one",
        )
        rid = row["id"] if row else None
        if rid:
            logger.info(
                "干预效果: %s distress_reduction=%.3f valence_improvement=%.3f",
                intervention_label, distress_reduction, valence_improvement,
            )
        return rid
    except Exception:
        logger.warning("干预效果记录失败", exc_info=True)
        return None


def get_best_interventions(
    session_id: str = "default", min_samples: int = 3
) -> list[dict]:
    """按平均 distress_reduction 排序输出最优干预.

    返回干预类型 + 样本数 + 平均效果指标.
    """
    rows = q(
        """SELECT intervention_type,
                  COUNT(*) as sample_count,
                  ROUND(AVG(distress_reduction)::numeric, 4) as avg_distress_reduction,
                  ROUND(AVG(valence_improvement)::numeric, 4) as avg_valence_improvement
           FROM intervention_outcomes
           WHERE session_id = %s AND intervention_type != 'skip'
           GROUP BY intervention_type
           HAVING COUNT(*) >= %s
           ORDER BY avg_distress_reduction DESC""",
        [session_id, min_samples],
    )
    return rows if rows else []


def get_recent_outcomes(
    session_id: str = "default", limit: int = 20
) -> list[dict]:
    """返回最近 N 条干预效果记录 (供 API 查询)."""
    rows = q(
        """SELECT id, turn_id, intervention_type, trigger_intent,
                  distress_reduction, valence_improvement,
                  created_at
           FROM intervention_outcomes
           WHERE session_id = %s
           ORDER BY id DESC LIMIT %s""",
        [session_id, limit],
    )
    result = []
    for r in (rows or []):
        d = dict(r)
        for key in ("created_at",):
            if d.get(key) and isinstance(d[key], datetime):
                d[key] = d[key].isoformat()
        result.append(d)
    return result
