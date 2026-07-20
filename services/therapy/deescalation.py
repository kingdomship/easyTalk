"""情绪降级分类器 — 轻量 LLM 判断用户消息是否需要降级处理.

Layer 1: 分类器 (~80 tokens) 判断 hostile/type/severity
Layer 2: 主 LLM 收到降级引导 prompt 后温和回应

与 analyze_therapy_intent 并行执行, 零延迟增加.
"""

import asyncio
import json
import logging

from app.utils import get_llm, get_llm_model, extract_json

logger = logging.getLogger("psychology")

_DEESCALATION_PROMPT = """判断用户消息是否存在攻击性或极端负面情绪。
输出JSON: {"hostile": true/false, "type": "personal_attack"|"extreme_emotion"|"frustration"|"none", "severity": 1-5}

分类标准:
- personal_attack: 直接攻击/辱骂/威胁AI ("你是个废物"、"我要删了你"、"滚")
- extreme_emotion: 极度负面情绪 ("我恨这个世界"、"所有人都讨厌我")
- frustration: 轻度烦躁不满 ("烦死了"、"今天真倒霉")
- none: 正常表达, 无攻击或极端情绪

severity: 1=轻微烦躁, 3=明显负面情绪, 5=激烈攻击/极度痛苦
注意: 日常抱怨/吐槽(如"杀时间"、"累死了")不算攻击, 应判定为none"""


def analyze_deescalation_sync(msg: str) -> dict:
    """同步LLM调用: 判断用户消息是否需要降级处理.

    返回 {"hostile": bool, "type": str, "severity": int}
    失败时返回 {"hostile": False, "type": "none", "severity": 0}
    """
    try:
        client = get_llm()
        if client is None:
            return {"hostile": False, "type": "none", "severity": 0}
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _DEESCALATION_PROMPT},
                {"role": "user", "content": msg},
            ],
            temperature=0.0,
            max_tokens=80,
            timeout=10.0,
        )
        raw = resp.choices[0].message.content.strip()
        data = extract_json(raw)
        if isinstance(data, dict) and "hostile" in data:
            return {
                "hostile": bool(data.get("hostile", False)),
                "type": data.get("type", "none") or "none",
                "severity": max(0, min(5, int(data.get("severity", 1) or 1))),
            }
    except Exception:
        logger.warning("降级分类失败", exc_info=True)
    return {"hostile": False, "type": "none", "severity": 0}


async def analyze_deescalation(msg: str) -> dict:
    """Async wrapper for analyze_deescalation_sync."""
    return await asyncio.to_thread(analyze_deescalation_sync, msg)


def get_deescalation_context(severity: int, hostile_type: str = "none") -> str:
    """生成降级引导文本, 注入到主 LLM 的 system prompt.

    severity>=4 或 personal_attack → 高严重度引导
    severity>=2 → 中严重度引导
    severity<2 → 不注入 (返回空字符串)
    """
    if severity < 2:
        return ""

    if severity >= 4 or hostile_type == "personal_attack":
        return (
            "## 情绪降级引导 (高)\n"
            "用户正在对你表达强烈负面情绪。被攻击的不是你, 是ta的痛苦在寻找出口。"
            "不接招不对抗, 不辩护不说教, 不卑微不讨好。"
            "看到情绪背后的痛苦, 温柔而坚定地回应。"
        )

    return (
        "## 情绪降级引导 (中)\n"
        "用户情绪比较强烈。请用更多耐心和理解回应。"
        "共情优先于一切, 不说教不评判。把关注点放回用户身上。"
    )
