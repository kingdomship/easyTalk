"""辩证行为疗法 (DBT) — TIPP 痛苦耐受 + 相反行动.

在现有 CBT/正念基础上增加:
- TIPP: 高 distress 时的生理干预（急性痛苦耐受）
- 相反行动: 情绪驱动的行为冲动 → 选择行为反方向的行动

通过 assemble_therapy_modules() 注入, 触发条件:
- panic > 0.5 且 fear > 0.5 → TIPP 技能
- 单一高激活负性情绪 → 相反行动指导
- deescalation severity >= 4 → TIPP 级干预
"""

# ── TIPP 痛苦耐受技能 ─────────────────────────────────────────

_TIPP_SKILLS = {
    "temperature": {
        "name": "温度刺激 (T)",
        "steps": [
            "用冷水拍脸，激活'潜水反射'——这会让你的身体自动放慢心跳",
            "握一块冰在手里，感受冰冷的触感",
            "洗个冷水脸，感受水流过皮肤的每一刻",
        ],
    },
    "intense_exercise": {
        "name": "剧烈运动 (I)",
        "steps": [
            "做20个开合跳或原地高抬腿",
            "用力甩动双手，像要把水甩干一样",
            "紧紧握拳5秒，然后突然松开——感受那种释放",
        ],
    },
    "paced_breathing": {
        "name": "节奏呼吸 (P)",
        "steps": [
            "盒式呼吸: 吸气4秒，屏住4秒，呼气4秒，停顿4秒。我们一起来一次？",
            "478呼吸: 用鼻子吸气4秒，屏住7秒，用嘴巴缓缓呼气8秒",
            "简单呼吸觉察: 不需要改变呼吸，只是注意到吸气...呼气...",
        ],
    },
    "paired_relaxation": {
        "name": "配对肌肉放松 (P)",
        "steps": [
            "依次收紧再放松每个肌群: 脚→小腿→大腿→腹部→胸部→手臂→肩膀→脸部",
            "收紧时吸气，放松时呼气",
            "注意到放松后的差异——哪里最明显？",
        ],
    },
}

# ── 相反行动映射 ──────────────────────────────────────────────

_OPPOSITE_ACTION_MAP = {
    "fear": {
        "urge": "逃避、回避、躲开",
        "question": "你的恐惧在告诉你逃避。如果反过来——去接近、去了解——会发生什么？",
        "opposite": "接近并探索: 搜集信息、小步骤面对、告诉自己'我可以处理'",
    },
    "rage": {
        "urge": "攻击、指责、发泄",
        "question": "如果不用对抗的方式，而是温和地表达你的感受呢？",
        "opposite": "温和离开或共情倾听: '我需要一些空间冷静下来' / 试着理解对方的处境",
    },
    "panic": {
        "urge": "封闭、麻木、放弃",
        "question": "此刻什么都感觉不到，那如果尝试一个小小的身体动作呢？",
        "opposite": "激活身体或寻求连接: 站起来走动、触摸有纹理的东西、给信任的人发一条简短消息",
    },
}


def _get_tipp_steps() -> str:
    """返回 TIPP 技能引导文本."""
    steps = []
    for key, skill in _TIPP_SKILLS.items():
        steps.append(f"- **{skill['name']}**: {skill['steps'][0]}")
    return "\n".join(steps)


def _get_opposite_action_text(affect: dict | None) -> str:
    """根据当前高激活负性情绪返回相反行动指导."""
    if not affect:
        return ""

    # Find dominant negative affect
    dominant = None
    max_val = 0
    for key in ["fear", "panic", "rage"]:
        val = affect.get(key, 0)
        if val > max_val:
            max_val = val
            dominant = key

    if not dominant or max_val < 0.3:
        return ""

    mapping = _OPPOSITE_ACTION_MAP.get(dominant, {})
    if not mapping:
        return ""

    return (
        f"注意: 用户可能正在体验{dominant_to_cn(dominant)}, 请温和地运用**相反行动**原则:\n"
        f"- 行动冲动: {mapping.get('urge', '')}\n"
        f"- 相反行动: {mapping.get('opposite', '')}\n"
        f"- 引导问题: {mapping.get('question', '')}\n"
        "- **不要评价或批评用户的感受** — 相反行动是邀请，不是命令"
    )


def dominant_to_cn(dominant: str) -> str:
    mapping = {"fear": "恐惧", "rage": "愤怒", "panic": "悲伤/恐慌"}
    return mapping.get(dominant, dominant)


def get_dbt_context(affect: dict | None = None, deescalation_severity: int = 0) -> str:
    """基于情感状态返回 DBT 干预上下文.

    触发条件:
    - panic > 0.5 且 fear > 0.5 → TIPP
    - deescalation severity >= 4 → TIPP
    - 单一高激活负性情绪 → 相反行动
    """
    parts = []

    if not affect:
        affect = {}

    panic = affect.get("panic", 0) if affect else 0
    fear = affect.get("fear", 0) if affect else 0

    if panic > 0.5 and fear > 0.5 or deescalation_severity >= 4:
        parts.append("## DBT 痛苦耐受（TIPP）\n用户处于高痛苦状态，请优先使用 TIPP 生理干预而非认知分析：")
        parts.append(_get_tipp_steps())
        parts.append("- 引导方式: '如果你愿意的话，我们可以试试...' / '来，跟我一起...'")
        parts.append("- 一次只用一个技能，不要连续推多个")
        parts.append("- 不要问'你感觉好点了吗' — TIPP 的目标是度过痛苦时刻，不是消除情绪")
    else:
        opposite = _get_opposite_action_text(affect)
        if opposite:
            parts.append("## DBT 情绪调节\n" + opposite)

    return "\n\n".join(parts) if parts else ""


def assemble_dbt_module(affect: dict | None = None, deescalation_severity: int = 0) -> str:
    """返回 DBT 提示词模块, 供 assemble_therapy_modules() 调用."""
    return get_dbt_context(affect, deescalation_severity)
