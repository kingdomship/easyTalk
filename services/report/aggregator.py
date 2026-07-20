"""报告聚合器 — 编排数据源, 生成 dashboard + AI 洞察, 持久化.

纯计算 + 可选 LLM, 每个数据源独立 try/catch, 部分失败不影响整体.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

# 里程碑标签映射
MILESTONE_LABELS = {7: "7天", 14: "14天", 21: "21天", 30: "30天", 60: "60天", 90: "90天"}


def _compute_valence_trend(date_from: date, date_to: date) -> dict:
    """从 risk_snapshot 计算效价趋势."""
    try:
        rows = q(
            """SELECT valence_ema, last_check_at FROM risk_snapshot
               WHERE last_check_at >= %s AND last_check_at <= %s
               ORDER BY last_check_at ASC""",
            [date_from, date_to + timedelta(days=1)],
        )
        if not rows or len(rows) < 2:
            return {"avg_valence": 0.5, "trend_direction": "stable", "sample_count": len(rows or [])}

        values = [float(r["valence_ema"] or 0.5) for r in rows]
        avg = sum(values) / len(values)
        # 简单线性回归
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = avg
        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        den = sum((i - x_mean) ** 2 for i in range(n))
        if den > 0 and y_mean > 0:
            slope = (num / den) / y_mean
        else:
            slope = 0

        if slope > 0.01:
            direction = "improving"
        elif slope < -0.01:
            direction = "declining"
        else:
            direction = "stable"

        return {"avg_valence": round(avg, 4), "trend_direction": direction,
                "trend_slope": round(slope, 6), "sample_count": n}
    except Exception:
        logger.warning("效价趋势计算失败", exc_info=True)
        return {"avg_valence": 0.5, "trend_direction": "stable", "sample_count": 0}


def _compute_affect_trend(date_from: date, date_to: date) -> dict:
    """从 affect_history 计算六维情感均值."""
    try:
        rows = q(
            """SELECT seeking, play, care, fear, rage, panic
               FROM affect_history
               WHERE date >= %s AND date <= %s
               ORDER BY date ASC""",
            [date_from, date_to],
        )
        if not rows:
            return {}
        dims = ["seeking", "play", "care", "fear", "rage", "panic"]
        result = {}
        for d in dims:
            vals = [float(r[d] or 0) for r in rows]
            result[d] = round(sum(vals) / len(vals), 4)
        return result
    except Exception:
        logger.warning("情感趋势计算失败", exc_info=True)
        return {}


def _compute_activity(date_from: date, date_to: date) -> dict:
    """对话活跃度统计."""
    try:
        row = q(
            """SELECT COUNT(*) as total_messages,
                      COUNT(DISTINCT DATE(created_at)) as active_days
               FROM chat_history
               WHERE created_at >= %s AND created_at <= %s""",
            [date_from, date_to + timedelta(days=1)],
            fetch="one",
        )
        if row:
            return {"total_messages": row["total_messages"], "active_days": row["active_days"]}
        return {"total_messages": 0, "active_days": 0}
    except Exception:
        logger.warning("活跃度统计失败", exc_info=True)
        return {"total_messages": 0, "active_days": 0}


def _get_behavioral_snapshot() -> dict | None:
    """获取最近一次行为标记."""
    try:
        from services.psych.behavioral_markers import get_latest_markers
        return get_latest_markers()
    except Exception:
        logger.warning("行为标记获取失败", exc_info=True)
        return None


def _get_intervention_ranking(date_from: date, date_to: date) -> list[dict]:
    """获取期间干预效果排名."""
    try:
        rows = q(
            """SELECT intervention_type,
                       COUNT(*) as sample_count,
                       ROUND(AVG(distress_reduction)::numeric, 4) as avg_distress_reduction,
                       ROUND(AVG(valence_improvement)::numeric, 4) as avg_valence_improvement
               FROM intervention_outcomes
               WHERE created_at >= %s AND created_at <= %s
                 AND intervention_type != 'skip'
               GROUP BY intervention_type
               HAVING COUNT(*) >= 1
               ORDER BY avg_distress_reduction DESC""",
            [date_from, date_to + timedelta(days=1)],
        )
        return rows if rows else []
    except Exception:
        logger.warning("干预效果排名失败", exc_info=True)
        return []


def _get_crisis_summary(date_from: date, date_to: date) -> dict:
    """危机事件摘要."""
    try:
        row = q(
            """SELECT COUNT(*) as total,
                      COUNT(*) FILTER (WHERE llm_verified) as verified,
                      MAX(severity) as max_severity,
                      COUNT(*) FILTER (WHERE acknowledged) as acknowledged
               FROM crisis_events
               WHERE created_at >= %s AND created_at <= %s""",
            [date_from, date_to + timedelta(days=1)],
            fetch="one",
        )
        if row:
            return {
                "total": row["total"],
                "verified": row["verified"] or 0,
                "max_severity": float(row["max_severity"] or 0),
                "acknowledged": row["acknowledged"] or 0,
            }
        return {"total": 0, "verified": 0, "max_severity": 0, "acknowledged": 0}
    except Exception:
        logger.warning("危机摘要失败", exc_info=True)
        return {"total": 0, "verified": 0, "max_severity": 0, "acknowledged": 0}


def _get_mood_distribution(date_from: date, date_to: date) -> dict:
    """情绪自检 emoji 分布."""
    try:
        rows = q(
            """SELECT mood_emoji, COUNT(*) as cnt
               FROM mood_checkins
               WHERE created_at >= %s AND created_at <= %s
               GROUP BY mood_emoji
               ORDER BY cnt DESC""",
            [date_from, date_to + timedelta(days=1)],
        )
        return {r["mood_emoji"]: r["cnt"] for r in rows} if rows else {}
    except Exception:
        logger.warning("情绪分布统计失败", exc_info=True)
        return {}


def _get_diary_count(date_from: date, date_to: date) -> int:
    """日记篇数."""
    try:
        row = q(
            """SELECT COUNT(*) as cnt FROM diary_entries
               WHERE date >= %s AND date <= %s""",
            [date_from, date_to],
            fetch="one",
        )
        return row["cnt"] if row else 0
    except Exception:
        logger.warning("日记统计失败", exc_info=True)
        return 0


def _get_latest_risk_snapshot() -> dict | None:
    """获取最近一次风险快照."""
    try:
        row = q(
            """SELECT * FROM risk_snapshot ORDER BY id DESC LIMIT 1""",
            fetch="one",
        )
        if not row:
            return None
        result = dict(row)
        for key in ("last_check_at", "created_at"):
            if result.get(key) and isinstance(result[key], datetime):
                result[key] = result[key].isoformat()
        return result
    except Exception:
        logger.warning("风险快照获取失败", exc_info=True)
        return None


def build_dashboard(date_from: date, date_to: date) -> dict:
    """构建完整仪表盘数据 (纯计算, 零 LLM 成本).

    每个数据源独立 try/catch, 部分失败不影响整体.
    """
    activity = _compute_activity(date_from, date_to)
    active_days = activity.get("active_days", 0)

    dashboard = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "active_days": active_days,
        "activity": activity,
        "affect_trend": _compute_affect_trend(date_from, date_to),
        "valence_summary": _compute_valence_trend(date_from, date_to),
        "interventions": _get_intervention_ranking(date_from, date_to),
        "crisis": _get_crisis_summary(date_from, date_to),
        "mood_distribution": _get_mood_distribution(date_from, date_to),
        "diary_count": _get_diary_count(date_from, date_to),
        "risk_snapshot": _get_latest_risk_snapshot(),
    }

    # 行为标记 (无时间过滤, 获取最新快照)
    behavior = _get_behavioral_snapshot()
    if behavior:
        dashboard["behavior"] = behavior

    return dashboard


def generate_report(
    date_from: date,
    date_to: date,
    report_type: str = "manual",
    milestone_label: str | None = None,
) -> int | None:
    """生成完整报告: 构建 dashboard + AI 洞察 + 持久化.

    返回: report_cache.id, 失败返回 None
    """
    from services.report.prompts import generate_llm_insight

    # 1. 构建仪表盘
    dashboard = build_dashboard(date_from, date_to)
    active_days = dashboard.get("active_days", 0)

    # 2. AI 洞察 (LLM 可选, 失败降级)
    ai_insight = generate_llm_insight(dashboard)

    # 3. 持久化
    try:
        row = q(
            """INSERT INTO report_cache
               (report_type, milestone_label, period_days, active_days,
                date_from, date_to, dashboard, ai_insight)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            [
                report_type,
                milestone_label,
                (date_to - date_from).days,
                active_days,
                date_from,
                date_to,
                json.dumps(dashboard, ensure_ascii=False, default=str),
                json.dumps(ai_insight, ensure_ascii=False),
            ],
            fetch="one",
        )
        rid = row["id"] if row else None
        logger.info(
            "报告生成: type=%s label=%s days=%d active=%d id=%s",
            report_type, milestone_label or "-", (date_to - date_from).days, active_days, rid,
        )
        return rid
    except Exception:
        logger.warning("报告持久化失败", exc_info=True)
        return None


def check_milestone():
    """检查是否到达里程碑 (活跃天数达到 7 的倍数).

    在 _post_reply_pipeline 中调用, 通过 background executor 异步执行.
    若满足条件且该里程碑尚无报告, 则生成里程碑报告.
    """
    from app.utils import get_background_executor

    try:
        row = q(
            "SELECT COUNT(DISTINCT DATE(created_at)) as active_days FROM chat_history",
            fetch="one",
        )
        if not row:
            return
        active_days = row["active_days"]
        if active_days < 7 or active_days % 7 != 0:
            return

        label = MILESTONE_LABELS.get(active_days, f"{active_days}天")

        # 检查是否已生成
        existing = q(
            """SELECT id FROM report_cache
               WHERE report_type = 'milestone' AND milestone_label = %s
               LIMIT 1""",
            [label],
            fetch="one",
        )
        if existing:
            return

        logger.info("检测到里程碑: %d 活跃天, 触发报告生成", active_days)
        today = date.today()
        date_from = today - timedelta(days=active_days)

        get_background_executor().submit(
            generate_report,
            date_from=date_from,
            date_to=today,
            report_type="milestone",
            milestone_label=label,
        )
    except Exception:
        logger.warning("里程碑检测失败", exc_info=True)


def get_latest_report() -> dict | None:
    """获取最新一份报告."""
    row = q(
        """SELECT * FROM report_cache ORDER BY created_at DESC LIMIT 1""",
        fetch="one",
    )
    if not row:
        return None
    return _format_report_row(row)


def list_reports(limit: int = 20) -> list[dict]:
    """返回报告历史列表 (精简字段, 不含完整 dashboard)."""
    rows = q(
        """SELECT id, report_type, milestone_label, period_days,
                  active_days, date_from, date_to, created_at
           FROM report_cache
           ORDER BY created_at DESC
           LIMIT %s""",
        [limit],
    )
    result = []
    for r in (rows or []):
        d = dict(r)
        for key in ("date_from", "date_to", "created_at"):
            if d.get(key) and isinstance(d[key], (date, datetime)):
                d[key] = d[key].isoformat()
        result.append(d)
    return result


def get_report_by_id(report_id: int) -> dict | None:
    """获取指定报告的完整数据."""
    row = q(
        "SELECT * FROM report_cache WHERE id = %s",
        [report_id],
        fetch="one",
    )
    if not row:
        return None
    return _format_report_row(row)


def _format_report_row(row: dict) -> dict:
    """格式化报告行: 解析 JSONB, 转换日期."""
    d = dict(row)
    for key in ("dashboard", "ai_insight"):
        if isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    for key in ("date_from", "date_to", "created_at"):
        if d.get(key) and isinstance(d[key], (date, datetime)):
            d[key] = d[key].isoformat()
    return d
