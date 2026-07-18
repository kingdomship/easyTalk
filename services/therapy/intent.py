"""治疗意图分析 — 独立轻量 prompt, 与 _INTENT_PROMPT 并行运行.

输出 intent 标签:
  - none: 普通闲聊
  - venting: 情绪宣泄, 需要倾听和共情
  - cbt_needed: 有认知扭曲迹象 (灾难化、非黑即白、过度概括)
  - mindfulness: 适合正念/grounding 引导
  - crisis: 危机信号 (交叉验证 crisis 模块)
"""

import json
import logging

logger = logging.getLogger("emoji-chat")

_THERAPY_INTENT_PROMPT = (
    "分析用户消息的治疗/辅导意图。仅输出JSON, 不要其他文字。\n"
    '{"intent": "none"|"venting"|"cbt_needed"|"mindfulness"|"crisis", "confidence": 0.0-1.0}\n'
    "- none: 普通闲聊, 不需要心理辅导\n"
    "- venting: 情绪宣泄, 需要倾听和共情, 不要急于给建议\n"
    "- cbt_needed: 有认知扭曲迹象 (灾难化/非黑即白/过度概括/个人化/应该思维)\n"
    "- mindfulness: 适合正念/grounding/当下觉察引导\n"
    "- crisis: 危机信号 (自伤/自杀/严重崩溃意图)"
)


def analyze_therapy_intent_sync(msg: str) -> dict:
    """同步分析治疗意图 (供 asyncio.to_thread 调用).

    返回: {"intent": str, "confidence": float}
    """
    try:
        from app.utils import get_llm, get_llm_model
        client = get_llm()
        if client is None:
            return {"intent": "none", "confidence": 0.0}
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _THERAPY_INTENT_PROMPT},
                {"role": "user", "content": msg},
            ],
            temperature=0.0,
            max_tokens=80,
            timeout=10.0,
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            intent = data.get("intent", "none")
            if intent not in ("none", "venting", "cbt_needed", "mindfulness", "crisis"):
                intent = "none"
            confidence = float(data.get("confidence", 0.0))
            return {"intent": intent, "confidence": min(1.0, max(0.0, confidence))}
    except Exception:
        logger.warning("therapy intent analysis failed", exc_info=True)
    return {"intent": "none", "confidence": 0.0}


async def analyze_therapy_intent(msg: str) -> dict:
    """异步分析治疗意图."""
    import asyncio
    return await asyncio.to_thread(analyze_therapy_intent_sync, msg)


def get_therapy_modules(intent: str) -> dict:
    """将治疗意图映射为 modules_config 格式.

    Phase 1: venting/crisis 有完整模块, cbt/mindfulness 为桩.
    """
    mapping = {
        "venting": {"therapy_venting": "full"},
        "cbt_needed": {"therapy_cbt": "compact"},
        "mindfulness": {"therapy_mindfulness": "compact"},
        "crisis": {"therapy_crisis": "full"},
        "none": {},
    }
    return mapping.get(intent, {})
