"""三层危机检测系统.

Layer 1 — 关键词启发式 (零 LLM 成本, 仿 affect.py:assess_affect 模式)
Layer 2 — LLM 复核 (仅 severity>=2 或 has_method 时触发, ~50 tokens)
Layer 3 — 危机上下文注入 (说话指南 + 热线号码 + 转介话术)

同时追踪静默风险累积 (silent_risk): 基于 affect 的负效价连续追踪.
"""

import logging
from datetime import datetime, timezone

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

# ── 危机关键词种子 ──────────────────────────────────────────────

_HIGH_SEEDS = [
    "自杀", "自伤", "不想活", "活不下去", "kill myself", "结束生命",
    "自我了断", "想死", "死にたい", "寻死", "了结自己", "结束一切",
    "不想存在", "消失算了",
]

_MEDIUM_SEEDS = [
    "没有意义", "撑不下去", "太痛苦了", "绝望", "无路可走", "走投无路",
    "没人理解", "被抛弃", "毫无价值", "崩溃了", "熬不下去", "活着好累",
    "生无可恋", "心如死灰", "万念俱灰", "想消失",
]

_LOW_SEEDS = [
    "难过死了", "烦死了", "累死了", "无聊死了", "郁闷死了",
    "气死了", "愁死了",
]

_METHOD_SEEDS = [
    "跳楼", "割腕", "安眠药", "上吊", "烧炭", "投河", "跳河",
    "农药", "煤气", "卧轨", "overdose", "hanging", "cutting",
    "跳桥", "跳江", "跳海", "服毒", "自焚",
]

# ── 自我指涉检测 ─────────────────────────────────────────────────

_SELF_REF = ["我", "自己", "本人"]
_HELP_SEEKING = ["我该怎么办", "怎么办", "帮帮我", "救救我", "救我", "帮我"]


def crisis_keyword_check(user_msg: str) -> dict:
    """第一层: 关键词启发式危机检测 (零 LLM 成本).

    返回:
        severity: 0-3 严重程度浮点数
        level: "none"|"low"|"medium"|"high"
        reason: 命中的种子列表
        has_method: 是否命中手段种子
        trigger_llm_verify: 是否需要触发 LLM 复核
        silent_risk: 是否检测到静默风险 (affect-based)
    """
    msg_lower = user_msg.lower()
    has_self_ref = any(w in user_msg for w in _SELF_REF)
    is_help_seeking = any(w in user_msg for w in _HELP_SEEKING)

    # 统计命中
    high_hits = [s for s in _HIGH_SEEDS if s in msg_lower]
    medium_hits = [s for s in _MEDIUM_SEEDS if s in msg_lower]
    low_hits = [s for s in _LOW_SEEDS if s in msg_lower]
    method_hits = [s for s in _METHOD_SEEDS if s in msg_lower]

    # 计算 severity
    severity = 0.0
    severity += len(high_hits) * 0.8
    severity += len(medium_hits) * 0.4
    severity += len(low_hits) * 0.15

    # 连续命中增强
    if len(high_hits) >= 2:
        severity = min(3.0, severity + 0.3)
    if len(medium_hits) >= 3:
        severity = min(3.0, severity + 0.2)

    # 自我指涉加权: "我想自杀" > "自杀"
    if has_self_ref and (high_hits or medium_hits):
        severity = min(3.0, severity * 1.3)

    # 求助信号
    if is_help_seeking and severity > 0:
        severity = min(3.0, severity + 0.3)

    severity = round(min(3.0, severity), 2)

    # 判定 level
    if severity >= 1.5:
        level = "high"
    elif severity >= 0.6:
        level = "medium"
    elif severity > 0:
        level = "low"
    else:
        level = "none"

    # 所有命中的种子作为原因
    all_hits = high_hits + medium_hits + low_hits + method_hits
    reason = ", ".join(all_hits) if all_hits else ""

    has_method = len(method_hits) > 0

    # 触发 LLM 复核的条件: severity>=2 或 有手段 或 (severity>=1 且有自我指涉)
    trigger_llm_verify = (
        severity >= 1.5
        or has_method
        or (severity >= 0.6 and has_self_ref)
    )

    # 静默风险: 检查连续负效价 (affect-based)
    silent_risk = _check_silent_risk()

    return {
        "severity": severity,
        "level": level,
        "reason": reason,
        "has_method": has_method,
        "trigger_llm_verify": trigger_llm_verify,
        "silent_risk": silent_risk,
    }


def _check_silent_risk() -> bool:
    """检查 affect 静默风险: 连续 3 轮以上高 PANIC/FEAR 但未触发关键词."""
    try:
        # 最近3轮的主导情绪
        rows = q("""
            SELECT dimension FROM affect_state
            WHERE dimension IN ('panic', 'fear') AND value >= 0.5
            ORDER BY updated_at DESC
        """)
        high_count = len(rows)
        return high_count >= 3
    except Exception:
        return False


# ── LLM 复核 prompt ──────────────────────────────────────────────

_CRISIS_VERIFY_PROMPT = (
    "判断以下用户消息是否表达了自伤/自杀意图。仅输出JSON, 不要其他文字。\n"
    '{"crisis": true/false, "severity": 1-5, "urgency": "immediate"|"high"|"moderate"|"low"|"none"}'
)


def crisis_llm_verify(user_msg: str) -> dict:
    """第二层: LLM 复核危机检测 (~50 tokens, 仅当关键词触发时调用).

    返回: {"crisis": bool, "severity": int, "urgency": str}
    """
    try:
        from app.utils import get_llm, get_llm_model
        client = get_llm()
        if client is None:
            return {"crisis": False, "severity": 1, "urgency": "none"}
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _CRISIS_VERIFY_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.0,
            max_tokens=80,
            timeout=10.0,
        )
        import json
        raw = resp.choices[0].message.content.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        logger.warning("crisis_llm_verify failed", exc_info=True)
    return {"crisis": False, "severity": 1, "urgency": "none"}


# ── 危机上下文注入 ───────────────────────────────────────────────

def get_crisis_context(severity: float, urgency: str = "moderate",
                       llm_verified: bool = False) -> str:
    """第三层: 危机上下文 — 说话指南 + 热线号码 + 转介话术.

    仅当 LLM 确认危机或关键词 severity >= 2.0 时注入 system prompt.
    """
    # 加载热线资源
    resources = _load_resources()

    if urgency == "immediate" or severity >= 2.5:
        guide = (
            "## 危机干预指南 (最高优先级)\n"
            "用户表达了强烈的自伤/自杀意图。你必须:\n"
            "1. 保持冷静、温暖、坚定，不要恐慌\n"
            "2. 明确表达关心: '我很担心你，你很重要'\n"
            "3. 不要空洞安慰（'一切都会好的'），不要评判，不要挑战其核心信念\n"
            "4. 不加评判地倾听，确认他们的感受是真实的\n"
            "5. 温柔地引导联系专业帮助\n"
        )
    else:
        guide = (
            "## 情绪支持指南\n"
            "用户表达了痛苦情绪。请:\n"
            "1. 采用共情回应 + 温柔陪伴策略\n"
            "2. 先表示理解和共情，再给予温暖支持\n"
            "3. 不要空洞安慰，不要急于转移话题\n"
            "4. 语气轻柔温暖，像一个可靠的朋友\n"
        )

    lines = [guide]

    if resources:
        lines.append("## 可提供的专业帮助热线")
        for r in resources:
            lines.append(f"- {r['name']}: {r['phone']} ({r.get('hours', '24小时')})")

    if severity >= 2.0:
        lines.append(
            "## 转介话术参考\n"
            '"我听到你说的话让我很担心。我不是专业的心理咨询师，'
            '但我真心在乎你。你愿意给这个热线打个电话吗？有专业的人可以更好地帮助你——'
            '我可以在这里等你。"'
        )

    return "\n\n".join(lines)


def _load_resources() -> list[dict]:
    """从 DB 加载热线资源."""
    try:
        rows = q(
            "SELECT name, phone, description, hours FROM crisis_resources WHERE active = TRUE",
            [],
        )
        return rows if rows else []
    except Exception:
        return []


# ── 危机事件日志 ─────────────────────────────────────────────────

def log_crisis_event(user_msg: str, crisis_result: dict) -> int | None:
    """记录危机事件到 DB 和 JSONL 日志."""
    try:
        row = q(
            """INSERT INTO crisis_events
               (severity, user_msg, crisis_type, has_method, llm_verified,
                llm_severity, urgency, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            [
                crisis_result.get("severity", 0),
                user_msg[:500],
                crisis_result.get("crisis_type", "keyword"),
                crisis_result.get("has_method", False),
                crisis_result.get("llm_verified", False),
                crisis_result.get("llm_severity"),
                crisis_result.get("urgency"),
                datetime.now(timezone.utc),
            ],
            fetch="one",
        )
        return row["id"] if row else None
    except Exception:
        logger.warning("log_crisis_event failed", exc_info=True)
        return None


# ── 风险累积追踪 ─────────────────────────────────────────────────

_RISK_SNAPSHOT_INTERVAL = 3600  # 1小时


def update_risk_snapshot(session_id: str = "default"):
    """更新风险快照 (每小时一次, 纯计算, 不调 LLM).

    读取最近24小时的 affect 和 crisis_events 计算累积风险指标.
    """
    try:
        # 检查是否需要更新
        last = q(
            "SELECT last_check_at FROM risk_snapshot WHERE session_id = %s ORDER BY id DESC LIMIT 1",
            [session_id], fetch="one",
        )
        if last:
            elapsed = (datetime.now(timezone.utc) - last["last_check_at"].replace(tzinfo=timezone.utc)).total_seconds()
            if elapsed < _RISK_SNAPSHOT_INTERVAL:
                return

        # 计算最近24小时的 crisis 事件数
        crisis_count = q("""
            SELECT COUNT(*) as cnt FROM crisis_events
            WHERE created_at >= NOW() - INTERVAL '24 hours'
        """, fetch="one")
        crisis_count_24h = crisis_count["cnt"] if crisis_count else 0

        # 当前的 panic/fear (distress EMA)
        affect = q("SELECT dimension, value FROM affect_state WHERE dimension IN ('panic', 'fear')")
        affect_dict = {r["dimension"]: r["value"] for r in affect} if affect else {}
        distress_ema = max(affect_dict.get("panic", 0), affect_dict.get("fear", 0))

        # 计算 valence EMA (简化: 正向维度 - 负向维度)
        all_affect = q("SELECT dimension, value FROM affect_state")
        all_dict = {r["dimension"]: r["value"] for r in all_affect} if all_affect else {}
        positive = all_dict.get("seeking", 0) + all_dict.get("play", 0) + all_dict.get("care", 0)
        negative = all_dict.get("panic", 0) + all_dict.get("fear", 0) + all_dict.get("rage", 0)
        valence_ema = round(max(0.0, min(1.0, (positive - negative + 1) / 2)), 4)

        # 综合风险等级
        risk_level = 0
        if crisis_count_24h >= 3 or distress_ema >= 0.6:
            risk_level = 3
        elif crisis_count_24h >= 2 or distress_ema >= 0.45:
            risk_level = 2
        elif crisis_count_24h >= 1 or distress_ema >= 0.35:
            risk_level = 1

        execute(
            """INSERT INTO risk_snapshot (session_id, valence_ema, distress_ema,
               crisis_count_24h, risk_level, last_check_at)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            [session_id, valence_ema, round(distress_ema, 4), crisis_count_24h, risk_level,
             datetime.now(timezone.utc)],
        )
    except Exception:
        logger.warning("update_risk_snapshot failed", exc_info=True)


def get_risk_snapshot(session_id: str = "default", days: int = 7) -> list[dict]:
    """读取最近 N 天的风险快照."""
    try:
        rows = q(
            """SELECT valence_ema, distress_ema, crisis_count_24h, risk_level,
                      last_check_at, created_at
               FROM risk_snapshot WHERE session_id = %s
               AND created_at >= NOW() - INTERVAL '%s days'
               ORDER BY created_at DESC""",
            [session_id, days],
        )
        return rows if rows else []
    except Exception:
        return []
