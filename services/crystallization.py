"""Pattern crystallization — persistent memory for repeated topics.

When a topic appears 3+ times across conversations, it is distilled by LLM
into a "crystal" — a one-sentence fact that persists across sessions and is
never lost to summarization compression.

Inspired by Echo's pattern crystallization: repeated interactions → permanent
knowledge nodes. Crystals are stored in memory/crystals.jsonl.
"""

import json
import logging
import os
import threading

logger = logging.getLogger("emoji-chat")

_BASE = os.path.dirname(os.path.dirname(__file__))
_CRYSTAL_PATH = os.path.join(_BASE, "memory", "crystals.jsonl")
_CHECK_EVERY = 10
_crystal_lock = threading.Lock()
_last_check_count = 0

_CRYSTALLIZE_PROMPT = """你是一个记忆分析助手。你需要从用户的多条消息中找出反复出现的话题或主题。

规则：
1. 只关注被提及3次或以上的话题/人物/事物/事件
2. 每个话题用一句话概括，像一条"记忆卡片"
3. 格式："话题名：一句话描述"
4. 如果没有任何话题出现3次以上，输出"无"
5. 最多提取3条

示例：
输入消息：
- 今天去看了朱砂手串
- 朋友送的手串断了，好难过
- 那串手串是我生日时收到的

输出：
朱砂手串：用户有一条意义重大的朱砂手串，是朋友送的生日礼物

直接输出结果，不要JSON格式。"""


def _count_lines() -> int:
    try:
        with open(_CRYSTAL_PATH) as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def _load_existing_tags() -> set[str]:
    """Load tag names from existing crystals to avoid duplicates."""
    tags = set()
    try:
        if os.path.exists(_CRYSTAL_PATH):
            with open(_CRYSTAL_PATH) as f:
                for line in f:
                    try:
                        c = json.loads(line)
                        tags.add(c.get("tag", ""))
                    except Exception:
                        pass
    except Exception:
        pass
    return tags


def _read_last_n_user_messages(n: int) -> list[str]:
    """Read the last N user messages from conversation archive."""
    archive = os.path.join(_BASE, "memory", "conversation_archive.jsonl")
    messages = []
    try:
        if os.path.exists(archive):
            with open(archive) as f:
                lines = f.readlines()
            for line in lines[-n * 2:]:  # roughly n*2 lines = n turns
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


def _crystallize_from_messages(messages: list[str], existing_tags: set[str]) -> list[dict]:
    """Call LLM to distill topic crystals from a list of user messages.

    Returns list of {"tag": str, "crystal": str} dicts, skipping existing tags.
    """
    if len(messages) < 5:
        return []

    from app.routes.chat import _get_llm
    client = _get_llm()

    numbered = "\n".join(f"- {m}" for m in messages[-20:])
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _CRYSTALLIZE_PROMPT},
                {"role": "user", "content": f"以下是最新的用户消息：\n\n{numbered}"},
            ],
            temperature=0.4,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
    except Exception:
        return []

    if not raw or raw == "无":
        return []

    crystals = []
    for line in raw.split("\n"):
        line = line.strip()
        if "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        parts = line.split(sep, 1)
        if len(parts) != 2:
            continue
        tag, desc = parts[0].strip(), parts[1].strip()
        if not tag or not desc or tag in existing_tags:
            continue
        if len(tag) > 40 or len(desc) < 4:
            continue
        crystals.append({"tag": tag, "crystal": desc})

    return crystals[:3]


def _save_crystals(crystals: list[dict]):
    """Append new crystals to crystals.jsonl."""
    if not crystals:
        return
    os.makedirs(os.path.dirname(_CRYSTAL_PATH), exist_ok=True)
    try:
        with open(_CRYSTAL_PATH, "a") as f:
            for c in crystals:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        logger.info("Crystallized %d memories: %s",
                     len(crystals),
                     [c["tag"] for c in crystals])
    except Exception:
        pass


def maybe_crystallize():
    """Check for recurring topics and distill crystal memories.

    Runs in a background thread after each chat turn. Only triggers
    every _CHECK_EVERY turns to avoid excessive LLM calls.
    """
    global _last_check_count
    if not _crystal_lock.acquire(blocking=False):
        return
    try:
        archive = os.path.join(_BASE, "memory", "conversation_archive.jsonl")
        if not os.path.exists(archive):
            return
        with open(archive) as f:
            line_count = sum(1 for _ in f)
        if line_count - _last_check_count < _CHECK_EVERY:
            return
        _last_check_count = line_count

        existing_tags = _load_existing_tags()
        messages = _read_last_n_user_messages(30)
        if len(messages) < 5:
            return

        new_crystals = _crystallize_from_messages(messages, existing_tags)
        _save_crystals(new_crystals)
    except Exception:
        pass
    finally:
        _crystal_lock.release()


def get_crystals() -> list[dict]:
    """Load all crystals, sorted by most recent first."""
    crystals = []
    try:
        if os.path.exists(_CRYSTAL_PATH):
            with open(_CRYSTAL_PATH) as f:
                for line in f:
                    try:
                        crystals.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return list(reversed(crystals))


def get_crystal_context() -> str:
    """Return crystal memories formatted for prompt injection.

    Use this in _build_context() to give the AI persistent memory
    of recurring topics.
    """
    crystals = get_crystals()
    if not crystals:
        return ""

    lines = ["## 用户反复提及的话题（已牢记）"]
    for c in crystals[:12]:  # cap at 12 to avoid prompt bloat
        lines.append(f"- {c['tag']}：{c['crystal']}")
    return "\n".join(lines)
