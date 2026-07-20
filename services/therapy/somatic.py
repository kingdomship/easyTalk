"""具身心理学 — 多迷走神经状态检测 + 自适应接地序列.

基于 Porges 多迷走神经理论, 从语言线索推断自主神经状态:
- ventral (腹侧迷走神经): 安全/社交参与
- sympathetic (交感神经): 战斗/逃跑
- dorsal (背侧迷走神经): 关闭/冻结

模式: 轻量 LLM 分类器 (~60 tokens) + affect 启发式 fallback.
"""

import json
import logging

logger = logging.getLogger("emoji-chat")

_POLYVAGAL_PROMPT = """分析用户消息的语言线索，推断自主神经状态。

三种状态:
- ventral: 安全、社交投入、开放 ("我感觉亲近" "我在乎你" 正常对话)
- sympathetic: 焦虑、紧迫、愤怒 ("我压力太大了" "我受够了" 急迫感)
- dorsal: 关闭、麻木、无力、绝望 ("我什么都感觉不到" "有什么意义呢" 平淡/沉默)

输出JSON:
{"state": "ventral"|"sympathetic"|"dorsal", "confidence": 0.0-1.0, "indicators": ["关键线索"]}

只输出JSON，不要附加其他文字。"""

# ── 三态接地序列 ─────────────────────────────────────────────

GROUNDING_SEQUENCES = {
    "ventral": {
        "label": "社交接地",
        "guidance": "用户处于安全状态，可以自然互动。保持温暖、开放的社交语气。",
        "exercises": [
            "跟我聊聊你今天过得怎么样？",
            "有什么有趣的事情想分享吗？",
        ],
    },
    "sympathetic": {
        "label": "身体运动接地",
        "guidance": "用户处于高唤醒状态（焦虑/愤怒），优先做身体层面的调节，不要急于认知分析。",
        "exercises": [
            "站起来做5次深呼吸，每次呼气时用力摇动手臂——把紧张感甩出去。",
            "试试'5-4-3-2-1感官接地': 你能看到的5样东西是什么？",
            "双脚用力踩在地板上，感受地面支撑着你。",
        ],
    },
    "dorsal": {
        "label": "存在性接地",
        "guidance": "用户处于关闭/麻木状态。目标不是'振奋'他，而是温和地承认他的存在。",
        "exercises": [
            "你在这里，你是安全的。我陪着你。",
            "感受地板支撑着你。不需要做任何事，只是呼吸。",
            "如果你愿意，可以把手放在胸口上。感受心跳——你在这里。",
        ],
    },
}


def map_affect_to_polyvagal(affect: dict | None) -> str | None:
    """情感→多迷走神经状态的启发式映射.

    LLM 分类失败时的 fallback, 零成本.
    """
    if not affect:
        return None

    fear = affect.get("fear", 0)
    rage = affect.get("rage", 0)
    panic = affect.get("panic", 0)
    seeking = affect.get("seeking", 0)
    play = affect.get("play", 0)
    care = affect.get("care", 0)

    # dorsal: 高 panic + 低 seeking → 关闭/麻木
    if panic > 0.4 and seeking < 0.3:
        return "dorsal"

    # sympathetic: 高 fear + rage → 战斗/逃跑
    if fear > 0.35 and rage > 0.35:
        return "sympathetic"
    if fear > 0.5 or rage > 0.5:
        return "sympathetic"

    # ventral: 高 care + play → 安全/社交
    if care > 0.3 or play > 0.3:
        return "ventral"

    # default: ventral (normal conversation mode)
    if seeking > 0.25:
        return "ventral"

    return None


def get_somatic_context(result: dict | None = None, affect: dict | None = None) -> str:
    """返回多迷走神经接地上下文.

    优先使用 LLM 分类结果, 失败时 fallback 到 affect 启发式.
    """
    state = None
    confidence = 0.0
    indicators = []

    if result and isinstance(result, dict):
        state = result.get("state")
        confidence = result.get("confidence", 0.0)
        indicators = result.get("indicators", [])

    # Fallback: affect heuristic
    if not state:
        state = map_affect_to_polyvagal(affect)
        confidence = 0.3  # lower confidence for heuristic

    if not state or state not in GROUNDING_SEQUENCES:
        return ""

    seq = GROUNDING_SEQUENCES[state]

    parts = [f"## 身体觉察引导 ({seq['label']})"]
    parts.append(seq["guidance"])
    parts.append("可用的接地练习:")
    for ex in seq["exercises"]:
        parts.append(f"- {ex}")

    if state in ("sympathetic", "dorsal"):
        parts.append("- 目标不是解决问题，而是帮助用户的身体感到安全")
        parts.append("- 邀请而非命令: '如果你愿意的话...' '我们来试试...'")
        parts.append("- 一次只用一个练习，不要连续推多个")

    if state == "dorsal":
        parts.append("- 不要问'你感觉好点了吗' — 关闭状态下这个问题会适得其反")
        parts.append("- 你的存在本身就是干预。安静陪伴也是强有力的回应")

    return "\n".join(parts)


async def analyze_polyvagal_state(user_message: str) -> dict | None:
    """轻量 LLM 分类器: 从语言线索推断多迷走神经状态.

    与 analyze_deescalation()、analyze_change_talk() 并行执行.
    失败时返回 None (降级到 affect 启发式 fallback).
    """
    if not user_message or len(user_message) < 4:
        return None

    try:
        import asyncio
        from app.utils import get_llm, get_llm_model

        loop = asyncio.get_event_loop()

        def _call():
            client = get_llm()
            if client is None:
                return None
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[
                    {"role": "system", "content": _POLYVAGAL_PROMPT},
                    {"role": "user", "content": user_message[:200]},
                ],
                temperature=0.1,
                max_tokens=60,
            )
            return resp.choices[0].message.content

        raw = await asyncio.to_thread(_call)
        if not raw:
            return None

        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        result = json.loads(raw[start:end])
        result["confidence"] = float(result.get("confidence", 0.0))
        return result
    except Exception:
        logger.warning("多迷走神经状态检测失败", exc_info=True)
        return None
