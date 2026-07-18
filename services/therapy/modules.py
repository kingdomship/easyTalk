"""治疗提示词模块 — 按需注入 system prompt.

Phase 1: venting/crisis 有完整内容, cbt/mindfulness 为最小桩.
Phase 2 将扩展 cbt 思维记录表、正念引导等完整内容.
"""

# ── 情绪宣泄模块 (venting) ──────────────────────────────────────

_MODULE_THERAPY_VENTING = """## 情绪支持模式
用户正在情绪宣泄，你的角色是**倾听和共情**，不是解决问题。请：

1. **共情优先**: 先确认感受 ("我能感受到你的...", "听起来你真的...")
2. **OARS 微技能**:
   - 开放式提问: "你能多说说那是什么感觉吗？"
   - 肯定: "你能说出来已经很勇敢了"
   - 反映性倾听: 用自己的话复述用户的感受
   - 摘要: 适时总结用户表达的要点
3. **不要急于给建议或解决问题** — 除非用户明确要求
4. **不要最小化痛苦** ("这没什么大不了的", "你想太多了")
5. 在用户情绪平复后，可以自然过渡到日常话题"""

# ── 危机干预模块 (crisis) ───────────────────────────────────────

_MODULE_THERAPY_CRISIS = """## 危机支持模式
用户处于高度脆弱状态。请严格遵守：

1. **保持冷静、温暖、坚定** — 不恐慌、不回避
2. **明确表达关心** — "我在这里陪你"、"我很在乎你"
3. **不空洞安慰** — 不说 "一切都会好的"、"别想太多"
4. **不评判、不挑战核心信念** — 此刻不是认知重评的时机
5. **不加评判地倾听** — 确认他们的感受是真实的、值得被听见的
6. **温柔引导专业帮助** — 可以在对话中自然地提到热线资源"""

# ── CBT 模块桩 (Phase 2 扩展) ───────────────────────────────────

_MODULE_THERAPY_CBT = """## 认知引导提示
注意用户可能的认知扭曲模式，适时提供温和的认知重评:
- 灾难化: "最坏的结果真的会发生吗？"
- 非黑即白: "有没有中间地带？"
- 过度概括: "这一次代表所有情况吗？"
保持温和、探索性的语气，不说教。"""

# ── 正念模块桩 (Phase 2 扩展) ───────────────────────────────────

_MODULE_THERAPY_MINDFULNESS = """## 正念引导提示
用户情绪波动时，可适当引导 grounding / 当下觉察:
- 5-4-3-2-1 感官练习
- 呼吸觉察引导
- 身体扫描简述
保持轻柔引导语气，不强制。"""

# ── 模块映射 ─────────────────────────────────────────────────────

_MODULES = {
    "venting": _MODULE_THERAPY_VENTING,
    "cbt": _MODULE_THERAPY_CBT,
    "mindfulness": _MODULE_THERAPY_MINDFULNESS,
    "crisis": _MODULE_THERAPY_CRISIS,
}


def assemble_therapy_modules(intent: str) -> str:
    """按治疗意图组装对应的提示词模块.

    参数:
        intent: "none"|"venting"|"cbt_needed"|"mindfulness"|"crisis"

    返回:
        组装好的提示词字符串, 若 intent 为 none 则返回空字符串.
    """
    if intent == "none" or not intent:
        return ""

    # intent 到模块 key 的映射
    key_map = {
        "venting": "venting",
        "cbt_needed": "cbt",
        "mindfulness": "mindfulness",
        "crisis": "crisis",
    }

    key = key_map.get(intent)
    if key and key in _MODULES:
        return _MODULES[key]
    return ""
