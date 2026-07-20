"""高级动机访谈 (MI) — 改变谈话检测与强化.

在 OARS 基础之上增加 DARN-CAT 改变谈话分类器,
帮助 AI 识别和强化用户的自发改变动机,
同时避免争论维持谈话或过早给出建议 (纠正反射).

模式: 轻量 LLM 分类器 (~60 tokens) + 降级式 _build_context 注入.
"""

import json
import logging

logger = logging.getLogger("emoji-chat")

_CHANGE_TALK_PROMPT = """分析用户的消息，判断其改变动机（改变谈话 vs 维持谈话）。

改变谈话 (Change Talk) — DARN: Desire (想要改变), Ability (有能力改变), Reason (改变的理由), Need (需要改变)
维持谈话 (Sustain Talk) — 为现状辩护、推迟行动、否认问题

输出JSON:
{"change_talk": 0.0-1.0, "sustain_talk": 0.0-1.0, "type": "desire"|"ability"|"reason"|"need"|"commitment"|"sustain"|"none", "topic": "改变的领域"}

只输出JSON，不要附加其他文字。"""


def get_mi_context(result: dict | None) -> str:
    """将 MI 分类结果转换为 prompt 注入文本.

    遵循 deescalation 模式: 由 chat.py 的 _build_context() 直接调用.
    不通过 assemble_therapy_modules() 注入.
    """
    if not result or not isinstance(result, dict):
        return ""

    ct = result.get("change_talk", 0.0)
    st = result.get("sustain_talk", 0.0)
    talk_type = result.get("type", "none")
    topic = result.get("topic", "")

    if ct < 0.3 and st < 0.3:
        return ""

    lines = ["## 动机访谈（MI）引导"]
    lines.append("注意用户的改变动机状态，调整你的回应方式：")

    if ct >= 0.5:
        if talk_type in ("desire", "ability", "reason", "need"):
            lines.append(f"- 用户表达了{talk_type_to_cn(talk_type)}（改变谈话），请**强化肯定**: '这听起来很重要。' / '你能意识到这点已经是一大步了。'")
        elif talk_type == "commitment":
            lines.append(f"- 用户表达了承诺性改变谈话，请**支持和具体化**: '你觉得第一步可以做什么？' / '有什么我可以帮忙的？'")
        if topic:
            lines.append(f"- 话题领域: {topic} — 可以围绕这个方向继续探索")

    if st >= 0.5:
        lines.append("- 用户表达了维持谈话，请不要争论或纠正。用**反映性倾听伴随**: '我听到你对改变有些犹豫，这很正常。'")
        lines.append("- 如果用户表达了矛盾（改变vs维持），可以温和引出**价值不一**: '你之前说过___对你很重要，这个选择是否与它一致？'")

    lines.append("- **避免纠正反射**: 不要急于给建议或解决方案，除非用户明确请求")
    return "\n".join(lines)


def talk_type_to_cn(t: str) -> str:
    mapping = {
        "desire": "改变的欲望",
        "ability": "改变的能力",
        "reason": "改变的理由",
        "need": "改变的需要",
        "commitment": "改变的承诺",
        "sustain": "维持现状",
    }
    return mapping.get(t, t)


async def analyze_change_talk(user_message: str) -> dict | None:
    """轻量 LLM 分类器: 检测用户消息中的改变/维持谈话.

    与 analyze_deescalation() 和 analyze_therapy_intent() 并行执行.
    失败或超时时返回 None (静默降级, 不影响主流程).
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
                    {"role": "system", "content": _CHANGE_TALK_PROMPT},
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
        result["change_talk"] = float(result.get("change_talk", 0))
        result["sustain_talk"] = float(result.get("sustain_talk", 0))
        return result
    except Exception:
        logger.warning("改变谈话检测失败", exc_info=True)
        return None
