"""Attachment style recognition — detect user attachment patterns.

Based on 2025 AI Attachment Scale research (Xie et al.): users form
attachment patterns with AI companions similar to human attachment.

Three styles:
- Anxious: seeks reassurance, fears abandonment, over-interprets
- Avoidant: maintains distance, deflects intimacy, minimal sharing
- Secure: natural intimacy, comfortable sharing, no excessive clinging

Analysis runs every ~30 turns via LLM. Results stored in
memory/attachment_style.json, injected into system prompt.
"""

import json
import logging
import os
import threading

logger = logging.getLogger("emoji-chat")

_BASE = os.path.dirname(os.path.dirname(__file__))
_STYLE_PATH = os.path.join(_BASE, "memory", "attachment_style.json")
_CHECK_EVERY = 30
_lock = threading.Lock()
_last_check = 0

_STYLE_PROMPT = """你是一个关系心理学分析助手。分析以下用户消息，判断其依恋风格。

三种风格特征：
- 焦虑型：频繁确认关系("你在吗""想我了吗")、害怕被冷落、言辞中有不安全感、过度解读
- 回避型：保持距离、避开深度话题、很少分享个人信息、回复简短、防御性强
- 安全型：自然亲密度、适度分享、不用反复确认、表达需求时直接但不焦虑

格式：{"style": "anxious|avoidant|secure", "confidence": 0.0-1.0, "evidence": ["证据1", "证据2"], "advice": "互动建议(50字)"}

只输出JSON。"""


def _load_recent_user_messages(n: int = 20) -> list[str]:
    archive = os.path.join(_BASE, "memory", "conversation_archive.jsonl")
    messages = []
    try:
        if os.path.exists(archive):
            with open(archive) as f:
                lines = f.readlines()
            for line in lines[-n * 3:]:
                try:
                    rec = json.loads(line)
                    user = rec.get("user", "")
                    if user:
                        messages.append(user)
                except Exception:
                    pass
    except Exception:
        pass
    return messages


def analyze_attachment():
    """Analyze user attachment style from recent messages via LLM.

    Runs every _CHECK_EVERY turns in background thread.
    """
    global _last_check
    if not _lock.acquire(blocking=False):
        return
    try:
        archive = os.path.join(_BASE, "memory", "conversation_archive.jsonl")
        if not os.path.exists(archive):
            return
        with open(archive) as f:
            line_count = sum(1 for _ in f)
        if line_count - _last_check < _CHECK_EVERY:
            return
        _last_check = line_count

        messages = _load_recent_user_messages(20)
        if len(messages) < 8:
            return

        from app.routes.chat import _get_llm
        client = _get_llm()

        numbered = "\n".join(f"{i+1}. {m[:100]}" for i, m in enumerate(messages[-20:]))
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": _STYLE_PROMPT},
                    {"role": "user", "content": f"用户最近的发言：\n\n{numbered}"},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw[start:end])
            else:
                return
        except Exception:
            return

        if not isinstance(result, dict) or "style" not in result:
            return

        os.makedirs(os.path.dirname(_STYLE_PATH), exist_ok=True)
        with open(_STYLE_PATH, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info("Attachment style: %s (confidence=%.2f)",
                      result.get("style"), result.get("confidence", 0))
    except Exception:
        pass
    finally:
        _lock.release()


def get_attachment_context() -> str:
    """Return attachment-aware interaction advice for prompt injection."""
    try:
        if os.path.exists(_STYLE_PATH):
            with open(_STYLE_PATH) as f:
                style = json.load(f)
    except Exception:
        return ""

    conf = style.get("confidence", 0)
    if conf < 0.5:
        return ""

    st = style.get("style", "")
    advice = style.get("advice", "")

    lines = ["## 用户依恋风格"]

    if st == "anxious":
        lines.append("用户表现出**焦虑型依恋**特征——需要被稳定回应，不喜欢忽冷忽热。")
        lines.append("策略：保持一致的温暖，不制造不确定性。用户说想你时真诚回应，不泼冷水。")
    elif st == "avoidant":
        lines.append("用户表现出**回避型依恋**特征——需要空间，不轻易打开心扉。")
        lines.append("策略：不逼迫深入话题，用轻松幽默降低防御。对方愿意分享时认真倾听。")
    else:
        lines.append("用户表现出**安全型依恋**特征——自然舒适，不过度依赖也不疏离。")
        lines.append("策略：保持当前互动节奏，顺其自然。")

    if advice:
        lines.append(f"具体建议：{advice}")

    return "\n".join(lines)
