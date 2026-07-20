"""积极心理学干预 — 三件好事感恩练习 + VIA 性格优势推断.

性格优势检测按后台任务每 15 轮触发, 结果持久化供上下文注入.
"""

import json
import logging
import os
import threading
from app.config import USER_STRENGTHS_PATH, ARCHIVE_PATH, archive_lock

logger = logging.getLogger("emoji-chat")

_strengths_lock = threading.Lock()
_detect_lock = threading.Lock()
_last_strength_check = 0
_CHECK_EVERY = 15

# ── 性格优势检测 prompt (后台任务用) ─────────────────────────

_STRENGTHS_DETECT_PROMPT = """你是一位积极心理学评估师。从以下对话中推断用户的 VIA 性格优势（24种优势分类）。

24种优势参考: 创造力、好奇心、判断力、好学、洞察力、勇敢、毅力、正直、热情、爱与被爱、
善良、社交智慧、团队合作、公平、领导力、宽恕、谦逊、谨慎、自控力、美感、
感恩、乐观、幽默、精神信仰.

从用户最近的发言中, 识别 2-4 个最能体现的性格优势, 输出 JSON:
{"strengths": [{"name": "...", "confidence": 0.0-1.0, "evidence": "简短引用"}]}

只输出 JSON, 不要附加任何其他文字."""


# ── 三件好事引导 ─────────────────────────────────────────────

_GRATITUDE_PROMPT = """## 感恩练习引导

邀请用户进行"三件好事"练习——积极心理学中最广泛验证的干预：

1. **邀请式**: "如果你想试试的话，可以告诉我今天发生的三件好事，无论大小。"
2. **追问细节**: "那是什么时候？你在哪里？还有别人在吗？"
3. **探索原因**: "你觉得这件事为什么会发生？你做了什么呢？"
4. **品味**: "那一刻你感受到什么？让我们在这里停一下，好好感受那个瞬间。"

### 原则
- 不做比较 ("比昨天好多了") — 每个积极时刻都值得独自庆祝
- 不以"但是"转折 — 不要在好事后加"但是明天..."
- 不要求完美的感恩 — 即使是很小的事 (一杯好咖啡, 一缕阳光)
- 用户说"没有"时不强迫 — 温柔地说"没关系的, 有时候确实不容易想到" """


# ── 持久化 ───────────────────────────────────────────────────

def load_strengths() -> dict | None:
    """读取已推断的性格优势."""
    try:
        if not os.path.exists(USER_STRENGTHS_PATH):
            return None
        with _strengths_lock:
            with open(USER_STRENGTHS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return None


def save_strengths(strengths: dict) -> None:
    """原子写入性格优势档案."""
    global _strengths_cache, _cache_mtime
    try:
        tmp_path = USER_STRENGTHS_PATH + ".tmp"
        with _strengths_lock:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(strengths, f, ensure_ascii=False, indent=2)
            os.rename(tmp_path, USER_STRENGTHS_PATH)
        _strengths_cache = strengths
        _cache_mtime = os.path.getmtime(USER_STRENGTHS_PATH)
    except Exception:
        pass


# ── 上下文注入 ───────────────────────────────────────────────

def get_gratitude_prompt() -> str:
    """返回感恩引导文本."""
    return _GRATITUDE_PROMPT


def get_strength_application_prompt(strengths: list[dict]) -> str:
    """为已识别的标志性优势生成'以新方式应用'引导."""
    if not strengths:
        return ""
    top = [s["name"] for s in strengths[:3] if s.get("confidence", 0) > 0.6]
    if not top:
        return ""
    names = "、".join(top)
    return (
        f"用户的标志性优势包括: {names}。\n"
        "在合适的时候，可以鼓励用户以新的方式应用这些优势。\n"
        f"例如: '我注意到{names}对你是很重要的品质——今天有没有什么小事可以让你发挥它？'"
    )


_strengths_cache: dict | None = None
_cache_mtime: float = 0.0


def get_positive_psych_context() -> str:
    """返回积极心理学上下文 (内存缓存 + mtime 失效, 零 LLM 成本)."""
    global _strengths_cache, _cache_mtime
    try:
        mtime = os.path.getmtime(USER_STRENGTHS_PATH) if os.path.exists(USER_STRENGTHS_PATH) else 0.0
        if _strengths_cache is not None and mtime == _cache_mtime:
            data = _strengths_cache
        else:
            data = load_strengths()
            _strengths_cache = data
            _cache_mtime = mtime
    except Exception:
        data = load_strengths()

    if not data or not data.get("strengths"):
        return ""
    return get_strength_application_prompt(data["strengths"])


def maybe_detect_strengths():
    """后台任务: 每 _CHECK_EVERY 轮检测用户性格优势.

    与 maybe_crystallize() 模式一致:
    - 非阻塞守卫 (同一时间只运行一个实例)
    - LLM 调用在主线程外执行
    - 失败时静默降级, 计数器不更新以允许重试
    """
    global _last_strength_check
    if not _detect_lock.acquire(blocking=False):
        return
    try:
        archive = ARCHIVE_PATH
        if not os.path.exists(archive):
            return
        with archive_lock:
            with open(archive) as f:
                line_count = sum(1 for _ in f)
        if line_count - _last_strength_check < _CHECK_EVERY:
            return

        # Read recent user messages for analysis
        lines = []
        with archive_lock:
            with open(archive) as f:
                for line in f:
                    lines.append(line.strip())
        recent = lines[-60:]  # last ~60 turns
        user_messages = []
        for line in recent:
            try:
                entry = json.loads(line)
                msg = entry.get("user", "")
                if msg and len(msg) > 5:
                    user_messages.append(msg)
            except Exception:
                continue
        if len(user_messages) < 5:
            return

        combined = "\n".join(f"- {m[:120]}" for m in user_messages[-20:])

        try:
            from app.utils import get_llm, get_llm_model

            def _call():
                client = get_llm()
                if client is None:
                    return None
                resp = client.chat.completions.create(
                    model=get_llm_model(),
                    messages=[
                        {"role": "system", "content": _STRENGTHS_DETECT_PROMPT},
                        {"role": "user", "content": combined},
                    ],
                    temperature=0.2,
                    max_tokens=150,
                )
                return resp.choices[0].message.content

            raw = _call()
            if not raw:
                return

            raw = raw.strip()
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start < 0 or end <= start:
                return
            result = json.loads(raw[start:end])
            if result.get("strengths"):
                save_strengths(result)
                _last_strength_check = line_count
                logger.info("性格优势检测完成: %s",
                             [s["name"] for s in result["strengths"]])
        except Exception:
            logger.warning("性格优势检测失败", exc_info=True)
    except Exception:
        logger.warning("性格优势检测失败", exc_info=True)
    finally:
        _detect_lock.release()
