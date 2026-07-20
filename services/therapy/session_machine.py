"""治疗会话状态机 — CBT 5步思维记录 + DBT 4步TIPP技能训练.

将单轮提示词注入升级为跨轮次步骤追踪, 状态持久化到 DB.
重启后未完成会话可恢复, 同一时间每种类型最多一个活跃会话.
"""

import logging
from datetime import datetime, timezone

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

# ── CBT 5 步思维记录 ──────────────────────────────────────────────

CBT_STEPS = [
    {
        "name": "情境",
        "question": "请描述一下发生了什么事情？什么时候、在哪里、和谁在一起？",
        "prompt": (
            "当前处于 CBT 思维记录第1步：**情境识别**。\n"
            "请引导用户描述具体事件：时间、地点、人物、发生了什么。\n"
            "鼓励客观描述事实（而非评价），用 '发生了什么' 而不是 '你感觉怎样'。\n"
            "如果用户已经描述了情境，确认理解后可以引导进入下一步。"
        ),
    },
    {
        "name": "自动思维",
        "question": "当时你脑海里冒出了什么想法？",
        "prompt": (
            "当前处于 CBT 思维记录第2步：**自动思维识别**。\n"
            "请引导用户回忆事发时脑海中自动冒出的想法或画面。\n"
            "帮助用户区分'想法'和'事实'：'你当时的想法是...?'。\n"
            "使用苏格拉底式提问：'这个想法的依据是什么？'"
        ),
    },
    {
        "name": "证据检验",
        "question": "支持和不支持这个想法的证据分别有哪些？",
        "prompt": (
            "当前处于 CBT 思维记录第3步：**证据检验**。\n"
            "引导用户分别列出支持和反对自动思维的证据。\n"
            "不做裁判，只帮助用户自己发现：'除了这些，还有什么？'\n"
            "注意认知扭曲模式（灾难化、非黑即白、过度概括等），但不直接贴标签。"
        ),
    },
    {
        "name": "替代思维",
        "question": "你能想到一个更平衡、更合理的想法吗？",
        "prompt": (
            "当前处于 CBT 思维记录第4步：**替代思维构建**。\n"
            "引导用户基于证据检验的结果，构建一个更平衡、更有帮助的想法。\n"
            "替代思维应该：1) 基于证据 2) 更平衡 3) 更有利于行动。\n"
            "避免空洞安慰（'往好的方面想'），聚焦具体可操作的新视角。"
        ),
    },
    {
        "name": "重评总结",
        "question": "现在重新看待这件事，你的感受有什么变化？",
        "prompt": (
            "当前处于 CBT 思维记录第5步：**重评与总结**。\n"
            "引导用户回顾整个思维记录过程，注意情绪和视角的变化。\n"
            "肯定用户的努力和觉察，总结学到的认知技能。\n"
            "强调这是一个可以反复练习的工具，而不只是一次性的练习。"
        ),
    },
]

# ── DBT TIPP 4 步技能训练 ──────────────────────────────────────────

DBT_STEPS = [
    {
        "name": "温度刺激 (T)",
        "question": "你愿意试试用冷水拍脸或者握一块冰吗？",
        "prompt": (
            "当前处于 DBT TIPP 第1步：**温度刺激**。\n"
            "引导用户使用冷水/冰块激活'潜水反射'，这会自然降低生理唤醒。\n"
            "具体指导：'用冷水拍脸10-15秒' 或 '握一块冰在手里'。\n"
            "重点是体验身体的物理变化，不需要'控制情绪'——身体自己会做出反应。"
        ),
    },
    {
        "name": "剧烈运动 (I)",
        "question": "我们一起做几个简单的身体动作？",
        "prompt": (
            "当前处于 DBT TIPP 第2步：**剧烈运动**。\n"
            "引导用户通过短暂高强度运动消耗应激能量。\n"
            "可选项：20个开合跳、原地高抬腿30秒、用力甩手。\n"
            "跟随用户的节奏，不强求完美执行——任何运动都是胜利。"
        ),
    },
    {
        "name": "节奏呼吸 (P)",
        "question": "跟我一起做一次呼吸练习好吗？",
        "prompt": (
            "当前处于 DBT TIPP 第3步：**节奏呼吸**。\n"
            "引导用户进行结构化呼吸练习。\n"
            "推荐盒式呼吸（吸气4秒-屏息4秒-呼气4秒-停顿4秒）。\n"
            "用文字节奏引导：'吸气...1...2...3...4...'。"
        ),
    },
    {
        "name": "渐进放松 (P)",
        "question": "我们从脚开始，慢慢放松全身好吗？",
        "prompt": (
            "当前处于 DBT TIPP 第4步：**渐进肌肉放松**。\n"
            "引导用户从下到上依次收紧再放松各肌群。\n"
            "顺序：脚→小腿→大腿→腹部→胸部→手臂→肩→脸。\n"
            "每个部位收紧5秒再放松，注意放松后的感觉。"
        ),
    },
]


def _steps_for(session_type: str) -> list[dict]:
    """返回指定类型的步骤列表."""
    if session_type == "cbt":
        return CBT_STEPS
    elif session_type == "dbt":
        return DBT_STEPS
    return []


# ── Session CRUD ───────────────────────────────────────────────────

def create_session(session_type: str) -> dict | None:
    """创建新会话. 同类型的活跃会话会先被标记为 abandoned."""
    # 停用旧会话
    execute(
        """UPDATE therapy_sessions SET status = 'abandoned', updated_at = %s
           WHERE session_type = %s AND status = 'active'""",
        [datetime.now(timezone.utc), session_type],
    )
    steps = _steps_for(session_type)
    if not steps:
        return None
    row = q(
        """INSERT INTO therapy_sessions
           (session_type, status, current_step, total_steps, step_names)
           VALUES (%s, 'active', 0, %s, %s) RETURNING id, created_at""",
        [session_type, len(steps), [s["name"] for s in steps]],
        fetch="one",
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "session_type": session_type,
        "status": "active",
        "current_step": 0,
        "total_steps": len(steps),
        "created_at": row["created_at"].isoformat(),
    }


def get_active_session(session_type: str | None = None) -> dict | None:
    """获取活跃会话. 不指定类型则返回任意活跃会话."""
    if session_type:
        row = q(
            """SELECT id, session_type, status, current_step, total_steps,
                      step_names, context, created_at, updated_at
               FROM therapy_sessions
               WHERE status = 'active' AND session_type = %s
               ORDER BY id DESC LIMIT 1""",
            [session_type], fetch="one",
        )
    else:
        row = q(
            """SELECT id, session_type, status, current_step, total_steps,
                      step_names, context, created_at, updated_at
               FROM therapy_sessions
               WHERE status = 'active'
               ORDER BY id DESC LIMIT 1""",
            fetch="one",
        )
    if not row:
        return None
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


def advance_step(
    session_id: int,
    user_input: str = "",
    ai_response: str = "",
    turn_id: int | None = None,
) -> dict | None:
    """推进到下一步. 返回更新后的会话状态."""
    session = q(
        "SELECT id, current_step, total_steps, step_names FROM therapy_sessions WHERE id = %s",
        [session_id], fetch="one",
    )
    if not session:
        return None

    cur = session["current_step"]
    steps = session["step_names"]
    if isinstance(steps, str):
        import json
        steps = json.loads(steps)

    # 记录当前步骤
    step_name = steps[cur] if cur < len(steps) else f"step_{cur}"
    execute(
        """INSERT INTO therapy_session_steps
           (session_id, step_index, step_name, user_input, ai_response, turn_id)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        [session_id, cur, step_name, user_input, ai_response, turn_id],
    )

    # 推进
    next_step = cur + 1
    new_status = "completed" if next_step >= session["total_steps"] else "active"
    execute(
        """UPDATE therapy_sessions SET current_step = %s, status = %s,
           updated_at = %s WHERE id = %s""",
        [next_step, new_status, datetime.now(timezone.utc), session_id],
    )

    logger.info(
        "会话步骤推进: %s step %s→%s (%s)",
        session_id, cur, next_step, new_status,
    )
    return get_active_session(
        session_type=q("SELECT session_type FROM therapy_sessions WHERE id = %s", [session_id], fetch="one")["session_type"]
    )


def get_step_prompt(session_type: str, step_index: int) -> str:
    """返回指定步骤的 prompt."""
    steps = _steps_for(session_type)
    if step_index < len(steps):
        return steps[step_index]["prompt"]
    return ""


def get_session_context() -> str | None:
    """返回当前活跃会话的上下文 prompt, 用于注入 _build_context.

    若 CBT 和 DBT 同时活跃, CBT 优先.
    """
    session = get_active_session("cbt") or get_active_session("dbt")
    if not session:
        return None

    stype = session["session_type"]
    step = session["current_step"]
    total = session["total_steps"]
    steps = session.get("step_names", []) if isinstance(session.get("step_names"), list) else _steps_for(stype)
    step_name = steps[step]["name"] if isinstance(steps, list) and step < len(steps) else f"第{step+1}步"
    prompt = get_step_prompt(stype, step)

    lines = [
        f"## 结构化治疗会话 ({stype.upper()}) — 第{step+1}/{total}步: {step_name}",
        prompt,
    ]

    if dev := q(
        "SELECT step_name, user_input FROM therapy_session_steps WHERE session_id = %s ORDER BY step_index",
        [session["id"]],
    ):
        lines.append("已完成的步骤摘要:")
        for d in dev:
            lines.append(f"- {d['step_name']}: {d['user_input'][:120]}")

    return "\n\n".join(lines)


# ── API helpers ────────────────────────────────────────────────────

def list_sessions(session_type: str | None = None, limit: int = 20) -> list[dict]:
    """列出最近的会话."""
    if session_type:
        rows = q(
            """SELECT id, session_type, status, current_step, total_steps,
                      created_at, updated_at
               FROM therapy_sessions WHERE session_type = %s
               ORDER BY id DESC LIMIT %s""",
            [session_type, limit],
        )
    else:
        rows = q(
            """SELECT id, session_type, status, current_step, total_steps,
                      created_at, updated_at
               FROM therapy_sessions
               ORDER BY id DESC LIMIT %s""",
            [limit],
        )
    result = []
    for r in (rows or []):
        d = dict(r)
        for key in ("created_at", "updated_at"):
            if d.get(key) and isinstance(d[key], datetime):
                d[key] = d[key].isoformat()
        result.append(d)
    return result


def get_session_detail(session_id: int) -> dict | None:
    """获取会话详情含步骤."""
    session = q(
        """SELECT id, session_type, status, current_step, total_steps,
                  step_names, context, created_at, updated_at
           FROM therapy_sessions WHERE id = %s""",
        [session_id], fetch="one",
    )
    if not session:
        return None
    d = dict(session)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    steps = q(
        """SELECT id, step_index, step_name, user_input, ai_response, turn_id, created_at
           FROM therapy_session_steps WHERE session_id = %s ORDER BY step_index""",
        [session_id],
    )
    d["steps"] = []
    for s in (steps or []):
        sd = dict(s)
        if sd.get("created_at") and isinstance(sd["created_at"], datetime):
            sd["created_at"] = sd["created_at"].isoformat()
        d["steps"].append(sd)
    return d
