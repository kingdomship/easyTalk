"""报告 AI 洞察 prompt 模板 + 规则降级叙事.

LLM 可用时调用 _INSIGHT_PROMPT 生成个性化洞察,
LLM 不可用时使用规则模板生成降级叙事.
"""

import logging

logger = logging.getLogger("emoji-chat")

_INSIGHT_PROMPT = """你是一位心理健康辅助AI的分析报告撰写者。请根据以下用户的心理健康数据，生成一段有温度、有洞察的分析报告。

## 报告期间
{date_from} 至 {date_to}，共 {active_days} 个活跃天

## 数据摘要
{data_summary}

## 要求
1. 以第二人称"你"称呼用户，语气温和但不煽情
2. 先总结整体状态（1-2句），再分2-3个要点展开
3. 每个要点结合具体数据，给出可操作的关怀建议
4. 不要做临床诊断，不要贴标签
5. 适当肯定用户的积极变化
6. 控制在200字以内
7. 用自然段落，不用编号或列表格式

请直接输出分析内容，不要加标题或前缀。"""


def build_data_summary(dashboard: dict) -> str:
    """将 dashboard JSON 转为 LLM 可读的文本摘要."""
    lines = []

    # 情绪六维
    affect = dashboard.get("affect_trend", {})
    if affect:
        dims = ["seeking", "play", "care", "fear", "rage", "panic"]
        labels = {"seeking": "探索", "play": "玩耍", "care": "关怀",
                  "fear": "恐惧", "rage": "愤怒", "panic": "恐慌"}
        items = []
        for d in dims:
            v = affect.get(d)
            if v is not None:
                items.append(f"{labels.get(d, d)}{v:.2f}")
        if items:
            lines.append(f"六维情绪均值: {', '.join(items)}")

    # 效价
    valence = dashboard.get("valence_summary", {})
    if valence:
        v_avg = valence.get("avg_valence")
        v_trend = valence.get("trend_direction", "stable")
        trend_cn = {"improving": "上升", "declining": "下降", "stable": "稳定"}
        if v_avg is not None:
            lines.append(f"情绪效价均值 {v_avg:.2f}，趋势{trend_cn.get(v_trend, v_trend)}")

    # 对话活跃度
    activity = dashboard.get("activity", {})
    if activity:
        lines.append(f"期间共 {activity.get('total_messages', 0)} 条对话")

    # 行为标记
    behavior = dashboard.get("behavior", {})
    if behavior:
        b_lines = []
        lt = behavior.get("latency_trend_direction")
        if lt == "increasing":
            b_lines.append("回复间隔有延长趋势")
        lst = behavior.get("length_trend_direction")
        if lst == "decreasing":
            b_lines.append("消息长度有缩短趋势")
        ln = behavior.get("late_night_ratio", 0)
        if ln > 0.3:
            b_lines.append(f"深夜消息占比 {ln*100:.0f}%")
        if b_lines:
            lines.append(f"行为观察: {'; '.join(b_lines)}")

    # 干预效果
    interventions = dashboard.get("interventions", [])
    if interventions:
        best = interventions[0]
        lines.append(
            f"最有效干预: {best.get('intervention_type', '未知')} "
            f"(痛苦缓解 {best.get('avg_distress_reduction', 0):.2f})"
        )

    # 危机
    crisis = dashboard.get("crisis", {})
    if crisis and crisis.get("total", 0) > 0:
        lines.append(f"期间检测到 {crisis['total']} 次危机信号")

    # 日记
    diaries = dashboard.get("diary_count", 0)
    if diaries:
        lines.append(f"记录了 {diaries} 篇日记")

    # 情绪分布
    mood_dist = dashboard.get("mood_distribution", {})
    if mood_dist:
        top = sorted(mood_dist.items(), key=lambda x: x[1], reverse=True)[:3]
        items = [f"{emoji}({cnt}次)" for emoji, cnt in top]
        lines.append(f"常用情绪标记: {', '.join(items)}")

    return "\n".join(lines)


def generate_llm_insight(dashboard: dict) -> dict:
    """调用 LLM 生成 AI 洞察.

    返回: {"insight": str, "key_findings": list[str], "suggestions": list[str]}
    """
    from app.utils import get_llm, get_llm_model

    data_summary = build_data_summary(dashboard)
    prompt = _INSIGHT_PROMPT.format(
        date_from=dashboard.get("date_from", ""),
        date_to=dashboard.get("date_to", ""),
        active_days=dashboard.get("active_days", 0),
        data_summary=data_summary,
    )

    client = get_llm()
    if not client:
        logger.warning("LLM 不可用, 使用规则降级叙事")
        return _fallback_insight(dashboard)

    try:
        model = get_llm_model()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一位温和而专业的心理健康分析助手。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=600,
        )
        insight_text = resp.choices[0].message.content.strip()
    except Exception:
        logger.warning("LLM 洞察生成失败, 降级为规则叙事", exc_info=True)
        return _fallback_insight(dashboard)

    # 提取关键发现和建议
    key_findings = _extract_key_findings(dashboard)
    suggestions = _generate_suggestions(dashboard)

    return {
        "insight": insight_text,
        "key_findings": key_findings,
        "suggestions": suggestions,
    }


def _fallback_insight(dashboard: dict) -> dict:
    """规则降级: 基于数据模板生成叙事."""
    active_days = dashboard.get("active_days", 0)
    date_from = dashboard.get("date_from", "")
    date_to = dashboard.get("date_to", "")

    parts = [f"在 {date_from} 至 {date_to} 的 {active_days} 天里，"]

    # 效价趋势
    valence = dashboard.get("valence_summary", {})
    v_trend = valence.get("trend_direction", "stable") if valence else "stable"
    if v_trend == "improving":
        parts.append("你的情绪整体呈上升趋势，这是一个积极的信号。")
    elif v_trend == "declining":
        parts.append("你的情绪似乎有些低落，这段时间可能不太容易。")
    else:
        parts.append("你的情绪状态总体平稳。")

    # 行为
    behavior = dashboard.get("behavior", {}) or {}
    if behavior.get("late_night_ratio", 0) > 0.3:
        parts.append("注意到你有不少深夜发消息的时候，记得照顾好自己的作息。")
    if behavior.get("latency_trend_direction") == "increasing":
        parts.append("你回复的间隔在变长，也许需要一些独处的空间——这完全没问题。")

    # 干预
    interventions = dashboard.get("interventions", [])
    if interventions:
        parts.append(f"在和你聊天的过程中，{interventions[0].get('intervention_type', '对话')}类的方式对你最有帮助。")

    # 危机
    crisis = dashboard.get("crisis", {}) or {}
    if crisis.get("total", 0) > 0:
        parts.append("这段时间出现过一些艰难的时刻，感谢你愿意在这里表达。")

    key_findings = _extract_key_findings(dashboard)
    suggestions = _generate_suggestions(dashboard)

    return {
        "insight": "".join(parts),
        "key_findings": key_findings,
        "suggestions": suggestions,
    }


def _extract_key_findings(dashboard: dict) -> list[str]:
    """从 dashboard 提取关键发现."""
    findings = []

    valence = dashboard.get("valence_summary", {})
    if valence:
        v_trend = valence.get("trend_direction", "")
        if v_trend == "improving":
            findings.append("情绪效价呈上升趋势")
        elif v_trend == "declining":
            findings.append("情绪效价有下降趋势，需要关注")

    behavior = dashboard.get("behavior", {}) or {}
    if behavior.get("late_night_ratio", 0) > 0.3:
        findings.append(f"深夜活跃度偏高 ({behavior['late_night_ratio']*100:.0f}%)")

    affect = dashboard.get("affect_trend", {})
    if affect:
        fear = affect.get("fear", 0)
        panic = affect.get("panic", 0)
        if fear + panic > 0.4:
            findings.append("负面情绪(恐惧+恐慌)水平较高")

    interventions = dashboard.get("interventions", [])
    if interventions:
        findings.append(f"最有效干预方式: {interventions[0].get('intervention_type', '未知')}")

    crisis = dashboard.get("crisis", {}) or {}
    if crisis.get("total", 0) > 0:
        findings.append(f"期间出现 {crisis['total']} 次危机信号")

    activity = dashboard.get("activity", {}) or {}
    if activity.get("total_messages", 0) > 0:
        findings.append(f"活跃对话 {activity['total_messages']} 条")

    return findings if findings else ["数据收集中，暂无显著发现"]


def _generate_suggestions(dashboard: dict) -> list[str]:
    """基于数据生成关怀建议."""
    suggestions = []

    behavior = dashboard.get("behavior", {}) or {}
    if behavior.get("late_night_ratio", 0) > 0.3:
        suggestions.append("尝试在睡前1小时放下手机，给大脑一个放松的缓冲期")
    if behavior.get("rhythm_stability", 0) < 0.3:
        suggestions.append("规律的作息有助于情绪稳定，可以尝试固定一个聊天时段")

    affect = dashboard.get("affect_trend", {}) or {}
    if affect.get("seeking", 0) < 0.2:
        suggestions.append("探索欲偏低时，不妨尝试一件从未做过的小事，激活新鲜感")
    if affect.get("play", 0) < 0.15:
        suggestions.append("适当增加一些娱乐和游戏时间，玩耍是情绪的天然调节器")
    if affect.get("fear", 0) + affect.get("panic", 0) > 0.4:
        suggestions.append("当恐惧和焦虑来袭时，试试深呼吸或正念冥想，回到当下")

    valence = dashboard.get("valence_summary", {}) or {}
    if valence.get("trend_direction") == "declining":
        suggestions.append("情绪低落时，和朋友或家人聊聊可能会有帮助")

    if not suggestions:
        suggestions.append("继续保持当前的节奏，你做得很好")

    return suggestions[:4]
