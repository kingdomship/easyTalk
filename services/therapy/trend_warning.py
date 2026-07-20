"""趋势预警 — 纯计算模块, 零 LLM 成本.

基于 risk_snapshot / crisis_events / behavioral_markers 数据,
检测三类趋势异常并生成预警:
- distress_rising: 痛苦指数连续上升
- rhythm_break: 社交节律中断
- crisis_accel: 危机事件频率加速

通过 SSE 推送到前端, 结果持久化到 trend_warnings 表.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

# ── 检测阈值 ──
DISTRESS_LOOKBACK_HOURS = 72
RHYTHM_RECENT_HOURS = 48
RHYTHM_BASELINE_HOURS = 96
CRISIS_ACCEL_DAYS = 7
MIN_SEVERITY_THRESHOLD = 0.2


def _is_duplicate(session_id: str, warning_type: str, hours: int = 6) -> bool:
    """检查最近 hours 小时内是否已有同类型预警."""
    row = q(
        """SELECT id FROM trend_warnings
           WHERE session_id = %s AND warning_type = %s
             AND created_at >= NOW() - INTERVAL '%s hours'
           LIMIT 1""",
        [session_id, warning_type, hours],
        fetch="one",
    )
    return row is not None


def detect_distress_rising(session_id: str = "default") -> dict | None:
    """检测 distress_ema 是否连续上升.

    读取最近 DISTRESS_LOOKBACK_HOURS 的 risk_snapshot,
    检查最近 3+ 个样本是否严格上升.
    """
    snapshots = q(
        """SELECT distress_ema, last_check_at FROM risk_snapshot
           WHERE session_id = %s
             AND last_check_at >= NOW() - INTERVAL '%s hours'
           ORDER BY last_check_at ASC""",
        [session_id, DISTRESS_LOOKBACK_HOURS],
    )
    if not snapshots or len(snapshots) < 3:
        return None

    values = [float(s["distress_ema"] or 0) for s in snapshots]
    last_three = values[-3:]

    if not (last_three[0] < last_three[1] < last_three[2]):
        return None

    rise_rate = (last_three[2] - last_three[0]) / max(len(values), 1)
    severity = min(1.0, rise_rate * 5)
    if severity < MIN_SEVERITY_THRESHOLD:
        return None

    return {
        "warning_type": "distress_rising",
        "severity": round(severity, 4),
        "details": {
            "current_ema": last_three[2],
            "previous_ema": last_three[0],
            "rise_amount": round(last_three[2] - last_three[0], 4),
            "sample_count": len(values),
        },
    }


def detect_rhythm_break(session_id: str = "default") -> dict | None:
    """检测社交节律中断.

    对比最近 48h 和之前 48h 的活跃小时分布, 使用香农熵衡量规律性变化.
    """
    recent = q(
        """SELECT EXTRACT(HOUR FROM created_at) AS hour FROM chat_history
           WHERE created_at >= NOW() - INTERVAL '%s hours'""",
        [RHYTHM_RECENT_HOURS],
    )
    baseline = q(
        """SELECT EXTRACT(HOUR FROM created_at) AS hour FROM chat_history
           WHERE created_at >= NOW() - INTERVAL '%s hours'
             AND created_at < NOW() - INTERVAL '%s hours'""",
        [RHYTHM_BASELINE_HOURS, RHYTHM_RECENT_HOURS],
    )
    if not baseline or len(baseline) < 5 or not recent or len(recent) < 3:
        return None

    def _hour_entropy(rows):
        hours = [int(r["hour"]) for r in rows if r.get("hour") is not None]
        if len(hours) < 2:
            return 0.0
        import math
        counts = Counter(hours)
        total = len(hours)
        entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
        return entropy

    baseline_entropy = _hour_entropy(baseline)
    recent_entropy = _hour_entropy(recent)

    if baseline_entropy <= 0:
        return None
    if recent_entropy <= baseline_entropy * 1.3:
        return None

    severity = min(1.0, (recent_entropy - baseline_entropy) / baseline_entropy)
    if severity < MIN_SEVERITY_THRESHOLD:
        return None

    return {
        "warning_type": "rhythm_break",
        "severity": round(severity, 4),
        "details": {
            "baseline_entropy": round(baseline_entropy, 4),
            "recent_entropy": round(recent_entropy, 4),
            "change_pct": round((recent_entropy - baseline_entropy) / baseline_entropy * 100, 1),
        },
    }


def detect_crisis_acceleration(session_id: str = "default") -> dict | None:
    """检测危机事件频率加速.

    将 CRISIS_ACCEL_DAYS 内的危机事件分为前后两半, 比较密度.
    """
    events = q(
        """SELECT created_at FROM crisis_events
           WHERE created_at >= NOW() - INTERVAL '%s days'
           ORDER BY created_at ASC""",
        [CRISIS_ACCEL_DAYS],
    )
    if not events or len(events) < 4:
        return None

    mid = len(events) // 2
    first_half = events[:mid]
    second_half = events[mid:]

    density_ratio = len(second_half) / max(len(first_half), 1)
    if density_ratio < 2.0:
        return None

    severity = min(1.0, (density_ratio - 1.0) / 3.0)
    if severity < MIN_SEVERITY_THRESHOLD:
        return None

    return {
        "warning_type": "crisis_accel",
        "severity": round(severity, 4),
        "details": {
            "first_half_count": len(first_half),
            "second_half_count": len(second_half),
            "density_ratio": round(density_ratio, 2),
            "total_events": len(events),
        },
    }


def check_all_trends(session_id: str = "default") -> list[dict]:
    """运行所有趋势检测器, 返回需要推送的活跃预警列表.

    去重: 同类型预警在 6h 内不重复写入.
    """
    warnings = []

    for detector, de_dup_hours in [
        (detect_distress_rising, 6),
        (detect_rhythm_break, 12),
        (detect_crisis_acceleration, 12),
    ]:
        try:
            result = detector(session_id)
            if not result:
                continue
            # 去重检查
            if _is_duplicate(session_id, result["warning_type"], de_dup_hours):
                continue
            warnings.append(result)
            # 持久化
            execute(
                """INSERT INTO trend_warnings
                   (session_id, warning_type, severity, details)
                   VALUES (%s, %s, %s, %s)""",
                [
                    session_id,
                    result["warning_type"],
                    result["severity"],
                    json.dumps(result["details"], ensure_ascii=False),
                ],
            )
            logger.info(
                "趋势预警: %s severity=%.3f", result["warning_type"], result["severity"]
            )
        except Exception:
            logger.warning(
                "趋势检测 %s 失败", detector.__name__, exc_info=True
            )
    return warnings


def get_active_warnings(session_id: str = "default", hours: int = 24) -> list[dict]:
    """获取最近 N 小时内的未确认预警 (供 API 查询)."""
    rows = q(
        """SELECT * FROM trend_warnings
           WHERE session_id = %s
             AND created_at >= NOW() - INTERVAL '%s hours'
           ORDER BY created_at DESC""",
        [session_id, hours],
    )
    result = []
    for r in (rows or []):
        d = dict(r)
        if isinstance(d.get("details"), str):
            try:
                d["details"] = json.loads(d["details"])
            except Exception:
                pass
        for key in ("created_at",):
            if d.get(key) and isinstance(d[key], datetime):
                d[key] = d[key].isoformat()
        result.append(d)
    return result
