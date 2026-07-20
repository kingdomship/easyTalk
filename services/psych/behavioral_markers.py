"""行为标记感知 — 纯计算模块, 零 LLM 成本.

分析 chat_history 表中的时序行为模式:
- 回复延迟趋势 (latency)
- 消息长度趋势 (length)
- 深夜活跃度 (late_night, 0-6点)
- 社交节律稳定性 (rhythm)

通过 APScheduler 每30分钟执行一次, 结果持久化到 behavioral_markers 表,
供趋势预警 (trend_warning.py) 和上下文注入使用.
"""

import logging
import statistics
from datetime import datetime, timedelta, timezone
from collections import Counter

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

WINDOW_HOURS = 24
SLOPE_SAMPLES_MIN = 5


def _compute_trend(values: list[float]) -> tuple[float, str]:
    """简单线性回归计算趋势斜率.

    返回: (slope, direction)
      direction: "increasing" | "decreasing" | "stable"
    """
    if len(values) < SLOPE_SAMPLES_MIN:
        return 0.0, "stable"
    n = len(values)
    if n < 2:
        return 0.0, "stable"
    x_mean = (n - 1) / 2.0
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0, "stable"
    slope = num / den
    # Normalize by y_mean for scale-independent comparison
    if y_mean > 0:
        slope = slope / y_mean
    if slope > 0.01:
        direction = "increasing"
    elif slope < -0.01:
        direction = "decreasing"
    else:
        direction = "stable"
    return round(slope, 6), direction


def analyze_latency(rows: list[dict]) -> dict:
    """分析用户回复延迟趋势 (相邻消息间隔).

    rows: chat_history 行列表, 按 id ASC 排序, 需含 created_at
    """
    latencies = []
    for i in range(1, len(rows)):
        prev = rows[i - 1].get("created_at")
        curr = rows[i].get("created_at")
        if prev and curr and isinstance(prev, datetime) and isinstance(curr, datetime):
            delta = (curr - prev).total_seconds()
            if 0 < delta < 86400:  # 过滤异常间隔 (>24h)
                latencies.append(delta)
    if not latencies:
        return {"avg_latency_seconds": 0, "latency_trend_slope": 0.0, "latency_trend_direction": "stable"}
    slope, direction = _compute_trend(latencies)
    return {
        "avg_latency_seconds": round(statistics.mean(latencies), 1),
        "latency_trend_slope": slope,
        "latency_trend_direction": direction,
    }


def analyze_length(rows: list[dict]) -> dict:
    """分析用户消息长度趋势.

    rows: chat_history 行列表, 需含 user_msg
    """
    lengths = []
    for r in rows:
        msg = r.get("user_msg", "")
        if msg:
            lengths.append(float(len(msg)))
    if not lengths:
        return {"avg_user_msg_length": 0, "length_trend_slope": 0.0, "length_trend_direction": "stable"}
    slope, direction = _compute_trend(lengths)
    return {
        "avg_user_msg_length": round(statistics.mean(lengths), 1),
        "length_trend_slope": slope,
        "length_trend_direction": direction,
    }


def analyze_late_night(rows: list[dict]) -> dict:
    """分析深夜活跃度 (凌晨 0-6 点)."""
    midnight_count = 0
    total = len(rows)
    for r in rows:
        ts = r.get("created_at")
        if ts and isinstance(ts, datetime) and 0 <= ts.hour < 6:
            midnight_count += 1
    return {
        "late_night_ratio": round(midnight_count / max(total, 1), 4),
        "late_night_frequency": midnight_count,
    }


def analyze_rhythm(rows: list[dict]) -> dict:
    """分析社交节律稳定性.

    - rhythm_stability: 1.0 = 每天同一时段发言, 0.0 = 完全随机
    - circadian_consistency: 最活跃时段的消息占比
    """
    hours_float = []
    for r in rows:
        ts = r.get("created_at")
        if ts and isinstance(ts, datetime):
            hours_float.append(ts.hour + ts.minute / 60.0)

    if len(hours_float) < 3:
        return {"rhythm_stability": 0.0, "preferred_hour": 12.0, "circadian_consistency": 0.0}

    # 最活跃的小时
    hour_buckets = Counter(int(h) for h in hours_float)
    preferred_hour = float(hour_buckets.most_common(1)[0][0])

    # 节律稳定性: 1 - 方差归一化
    variance = statistics.variance(hours_float) if len(hours_float) > 1 else 0.0
    stability = max(0.0, 1.0 - variance / 12.0)

    # 节律一致性: 最活跃时段占比
    peak_count = hour_buckets.get(int(preferred_hour), 0)
    consistency = peak_count / max(len(hours_float), 1)

    return {
        "rhythm_stability": round(stability, 4),
        "preferred_hour": preferred_hour,
        "circadian_consistency": round(consistency, 4),
    }


def compute_behavioral_markers(session_id: str = "default") -> dict | None:
    """主入口: 分析最近 WINDOW_HOURS 小时的行为模式并持久化.

    由 APScheduler 每30分钟调用一次.
    纯计算, 零 LLM 成本.
    """
    window_start = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    rows = q(
        """SELECT id, user_msg, created_at FROM chat_history
           WHERE created_at >= %s ORDER BY id ASC""",
        [window_start],
    )
    if not rows or len(rows) < 3:
        return None

    window_end = datetime.now(timezone.utc)

    latency = analyze_latency(rows)
    length = analyze_length(rows)
    late_night = analyze_late_night(rows)
    rhythm = analyze_rhythm(rows)

    # 合并所有标记
    markers = {}
    markers.update(latency)
    markers.update(length)
    markers.update(late_night)
    markers.update(rhythm)

    # 写入 DB (去重: 同一窗口只写一次)
    existing = q(
        """SELECT id FROM behavioral_markers
           WHERE window_start = %s AND session_id = %s LIMIT 1""",
        [window_start, session_id],
        fetch="one",
    )
    if not existing:
        execute(
            """INSERT INTO behavioral_markers
               (session_id, window_start, window_end,
                avg_latency_seconds, latency_trend_slope, latency_trend_direction,
                avg_user_msg_length, length_trend_slope, length_trend_direction,
                late_night_ratio, late_night_frequency,
                rhythm_stability, preferred_hour, circadian_consistency)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                session_id, window_start, window_end,
                markers.get("avg_latency_seconds", 0),
                markers.get("latency_trend_slope", 0),
                markers.get("latency_trend_direction", "stable"),
                markers.get("avg_user_msg_length", 0),
                markers.get("length_trend_slope", 0),
                markers.get("length_trend_direction", "stable"),
                markers.get("late_night_ratio", 0),
                markers.get("late_night_frequency", 0),
                markers.get("rhythm_stability", 0),
                markers.get("preferred_hour", 12),
                markers.get("circadian_consistency", 0),
            ],
        )

    return markers


def get_behavioral_context(session_id: str = "default") -> str:
    """生成可注入 system prompt 的行为标记摘要.

    零 LLM 成本, 仅从最新一条 behavioral_markers 记录生成.
    当检测到异常行为模式时返回非空字符串.
    """
    row = q(
        """SELECT * FROM behavioral_markers
           WHERE session_id = %s ORDER BY id DESC LIMIT 1""",
        [session_id],
        fetch="one",
    )
    if not row:
        return ""

    alerts = []
    if row.get("latency_trend_direction") == "increasing":
        alerts.append("用户回复间隔有延长趋势, 注意动力或投入度变化")
    if row.get("length_trend_direction") == "decreasing":
        alerts.append("用户消息长度有缩短趋势, 注意投入度或情绪变化")
    if row.get("late_night_ratio", 0) > 0.3:
        cnt = row.get("late_night_frequency", 0)
        alerts.append(f"近24h有{cnt}条消息在凌晨发送, 关注睡眠节律")
    if row.get("rhythm_stability", 0) > 0.6:
        t = int(row.get("preferred_hour", 12))
        alerts.append(f"社交节律稳定, 活跃时段约在{t}:00前后")

    return "【行为观察】" + "；".join(alerts) if alerts else ""


def get_latest_markers(session_id: str = "default") -> dict | None:
    """获取最近一次行为标记结果 (供 API 查询)."""
    row = q(
        """SELECT * FROM behavioral_markers
           WHERE session_id = %s ORDER BY id DESC LIMIT 1""",
        [session_id],
        fetch="one",
    )
    if not row:
        return None
    # Convert datetime to string for JSON
    result = dict(row)
    for key in ("window_start", "window_end", "computed_at"):
        if result.get(key) and isinstance(result[key], datetime):
            result[key] = result[key].isoformat()
    return result
