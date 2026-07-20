"""心理健康辅助 API 端点 — 危机日志、热线资源、风险评估."""

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.db import q, execute
from services.therapy.models import AcknowledgeRequest

router = APIRouter(prefix="/api/therapy", tags=["therapy"])


@router.get("/crisis-log")
async def crisis_log(days: int = Query(default=30, ge=1, le=365)):
    """返回最近 N 天的危机事件列表."""
    try:
        rows = q(
            """SELECT id, severity, crisis_type, has_method, llm_verified,
                      llm_severity, urgency, acknowledged, created_at
               FROM crisis_events
               WHERE created_at >= NOW() - INTERVAL '%s days'
               ORDER BY created_at DESC LIMIT 200""",
            [days],
        )
        return {"events": rows if rows else []}
    except Exception:
        return {"events": [], "error": "crisis_events 表可能尚未创建"}


@router.get("/resources")
async def get_resources():
    """返回可用的心理援助热线资源."""
    try:
        rows = q(
            """SELECT id, name, phone, description, country, hours
               FROM crisis_resources WHERE active = TRUE ORDER BY id""",
        )
        return {"resources": rows if rows else []}
    except Exception:
        return {"resources": [], "error": "crisis_resources 表可能尚未创建"}


@router.post("/acknowledge")
async def acknowledge(req: AcknowledgeRequest):
    """标记危机事件为已处理."""
    try:
        affected = execute(
            """UPDATE crisis_events SET acknowledged = TRUE,
               acknowledged_at = %s WHERE id = %s AND acknowledged = FALSE""",
            [datetime.now(timezone.utc), req.event_id],
        )
        if affected and affected > 0:
            return {"ok": True, "event_id": req.event_id}
        return {"ok": False, "error": "事件不存在或已处理"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/dashboard")
async def dashboard(days: int = Query(default=7, ge=1, le=90)):
    """返回脱敏统计数据: 危机事件数、严重等级分布、风险快照.

    不暴露具体消息内容, 仅返回聚合统计数据.
    """
    try:
        # 危机事件统计
        total = q(
            """SELECT COUNT(*) as cnt FROM crisis_events
               WHERE created_at >= NOW() - INTERVAL '%s days'""",
            [days], fetch="one",
        )
        by_severity = q(
            """SELECT
                 CASE
                   WHEN severity >= 2.0 THEN 'high'
                   WHEN severity >= 1.0 THEN 'medium'
                   ELSE 'low'
                 END as level,
                 COUNT(*) as cnt
               FROM crisis_events
               WHERE created_at >= NOW() - INTERVAL '%s days'
               GROUP BY level""",
            [days],
        )
        llm_verified = q(
            """SELECT COUNT(*) as cnt FROM crisis_events
               WHERE created_at >= NOW() - INTERVAL '%s days'
               AND llm_verified = TRUE""",
            [days], fetch="one",
        )
        unacknowledged = q(
            """SELECT COUNT(*) as cnt FROM crisis_events
               WHERE acknowledged = FALSE""",
            fetch="one",
        )

        # 最新风险快照
        snapshots = q(
            """SELECT valence_ema, distress_ema, crisis_count_24h,
                      risk_level, last_check_at
               FROM risk_snapshot
               WHERE created_at >= NOW() - INTERVAL '%s days'
               ORDER BY created_at DESC LIMIT 30""",
            [days],
        )

        return {
            "period_days": days,
            "total_events": total["cnt"] if total else 0,
            "by_severity": {r["level"]: r["cnt"] for r in by_severity} if by_severity else {},
            "llm_verified_count": llm_verified["cnt"] if llm_verified else 0,
            "unacknowledged_count": unacknowledged["cnt"] if unacknowledged else 0,
            "risk_snapshots": snapshots if snapshots else [],
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/cbt-record")
async def save_cbt_record(
    situation: str = "",
    auto_thought: str = "",
    evidence_for: str = "",
    evidence_against: str = "",
    alternative: str = "",
    reframed: str = "",
):
    """保存 CBT 思维记录."""
    from fastapi import Body
    row = q(
        """INSERT INTO cbt_records (situation, auto_thought, evidence_for,
           evidence_against, alternative, reframed)
           VALUES (%s, %s, %s, %s, %s, %s)
           RETURNING id""",
        [str(situation), str(auto_thought), str(evidence_for),
         str(evidence_against), str(alternative), str(reframed)],
        fetch="one",
    )
    return {"ok": True, "id": row["id"] if row else None}


@router.get("/cbt-records")
async def list_cbt_records(days: int = Query(default=30, ge=1, le=365)):
    """返回最近 N 天的 CBT 记录列表."""
    rows = q(
        "SELECT id, auto_thought, reframed, created_at FROM cbt_records "
        "WHERE created_at >= NOW() - INTERVAL '%s days' "
        "ORDER BY created_at DESC LIMIT 50",
        [days],
    )
    return rows if rows else []


@router.get("/intervention-insights")
async def intervention_insights(min_samples: int = Query(default=3, ge=1, le=50)):
    """返回按 distress_reduction 排序的最优干预, 用于个性化治疗匹配."""
    from services.therapy.outcome import get_best_interventions, get_recent_outcomes
    best = get_best_interventions(min_samples=min_samples)
    recent = get_recent_outcomes(limit=20)
    return {
        "best_interventions": best,
        "recent_outcomes": recent,
    }
