"""Pattern crystallization — persistent memory for repeated topics.

When a topic appears 3+ times across conversations, it is distilled by LLM
into a "crystal" — a one-sentence fact that persists across sessions and is
never lost to summarization compression.

Inspired by Echo's pattern crystallization: repeated interactions → permanent
knowledge nodes. Crystals are stored in memory/crystals.jsonl.
"""

import json
import logging
import math
import os
import shutil
import threading

logger = logging.getLogger("emoji-chat")

from app.config import ARCHIVE_PATH, CRYSTAL_PATH, MEMORY_DIR, archive_lock

_CHECK_EVERY = 10
_crystal_lock = threading.RLock()
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
        with _crystal_lock:
            with open(CRYSTAL_PATH) as f:
                return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def _load_existing_tags() -> set[str]:
    """Load tag names from existing crystals to avoid duplicates."""
    tags = set()
    try:
        if os.path.exists(CRYSTAL_PATH):
            with _crystal_lock:
                with open(CRYSTAL_PATH) as f:
                    for line in f:
                        try:
                            c = json.loads(line)
                            tags.add(c.get("tag", ""))
                        except Exception:
                            logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return tags


def _read_last_n_user_messages(n: int) -> list[str]:
    """Read the last N user messages from conversation archive."""
    archive = ARCHIVE_PATH
    messages = []
    try:
        if os.path.exists(archive):
            from collections import deque
            with archive_lock:
                with open(archive) as f:
                    last_lines = list(deque(f, maxlen=n * 2))
            for line in last_lines:  # roughly n*2 lines = n turns
                try:
                    rec = json.loads(line)
                    user = rec.get("user", "")
                    if user:
                        messages.append(user)
                except Exception:
                    logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return messages


def _crystallize_from_messages(messages: list[str], existing_tags: set[str]) -> list[dict]:
    """Call LLM to distill topic crystals from a list of user messages.

    Returns list of {"tag": str, "crystal": str} dicts, skipping existing tags.
    """
    if len(messages) < 5:
        return []

    from app.utils import get_llm, get_llm_model
    client = get_llm()
    if client is None:
        return []

    numbered = "\n".join(f"- {m}" for m in messages[-20:])
    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _CRYSTALLIZE_PROMPT},
                {"role": "user", "content": f"以下是最新的用户消息：\n\n{numbered}"},
            ],
            temperature=0.4,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
    except Exception:
        logger.warning("Operation failed", exc_info=True)
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
    """Append new crystals to crystals.jsonl with salience-weighted importance."""
    if not crystals:
        return
    os.makedirs(os.path.dirname(CRYSTAL_PATH), exist_ok=True)

    # Read current salience for importance weighting
    sal_base = 0.5
    try:
        from services.emotion.salience import get_salience
        s = get_salience()
        if s:
            # High surprise + high reward → more important memory
            surprise = s.get("surprise", 0.1)
            reward = s.get("reward", 0.1)
            sal_base = 0.4 + (surprise * 0.3) + (reward * 0.3)
    except Exception:
        logger.warning("Operation failed", exc_info=True)

    try:
        with _crystal_lock:
            with open(CRYSTAL_PATH, "a") as f:
                for c in crystals:
                    c["importance"] = round(min(1.0, sal_base), 3)
                    c["reinforcement_count"] = 1
                    c["last_reinforced"] = 0
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
        logger.info("Crystallized %d memories (base_imp=%.2f): %s",
                     len(crystals), sal_base,
                     [c["tag"] for c in crystals])
    except Exception:
        logger.warning("Operation failed", exc_info=True)


def maybe_crystallize():
    """Check for recurring topics and distill crystal memories.

    Runs in a background thread after each chat turn. Only triggers
    every _CHECK_EVERY turns to avoid excessive LLM calls.
    """
    global _last_check_count
    if not _crystal_lock.acquire(blocking=False):
        return
    try:
        archive = ARCHIVE_PATH
        if not os.path.exists(archive):
            return
        with archive_lock:
            with open(archive) as f:
                line_count = sum(1 for _ in f)
        if line_count - _last_check_count < _CHECK_EVERY:
            return

        existing_tags = _load_existing_tags()
        messages = _read_last_n_user_messages(30)
        if len(messages) < 5:
            return

        new_crystals = _crystallize_from_messages(messages, existing_tags)
        _save_crystals(new_crystals)
        _last_check_count = line_count
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    finally:
        _crystal_lock.release()


def get_crystals(min_importance: float = 0.2) -> list[dict]:
    """Load active crystals with Ebbinghaus decay applied.

    Crystals decay over time unless reinforced. Those below min_importance
    are marked dormant and excluded from prompt injection.
    """
    crystals = []
    archive_path = ARCHIVE_PATH
    total_turns = 0
    try:
        if os.path.exists(archive_path):
            with archive_lock:
                with open(archive_path) as f:
                    total_turns = sum(1 for _ in f)
    except Exception:
        logger.warning("Operation failed", exc_info=True)

    try:
        if os.path.exists(CRYSTAL_PATH):
            with _crystal_lock, open(CRYSTAL_PATH) as f:
                for line in f:
                    try:
                        c = json.loads(line)
                        imp = c.get("importance", 0.5)
                        last = c.get("last_reinforced", 0)
                        count = c.get("reinforcement_count", 1)

                        # Ebbinghaus decay: importance decays with turns since last reinforcement
                        # More reinforcements → slower decay (consolidation)
                        turns_since = max(0, total_turns - last)
                        decay_rate = 0.02 / math.sqrt(count)  # slower with more reinforcements
                        imp *= math.exp(-decay_rate * turns_since)

                        c["current_importance"] = round(imp, 3)
                        c["dormant"] = imp < 0.3
                        crystals.append(c)
                    except Exception:
                        logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return sorted(crystals, key=lambda c: c.get("current_importance", 0), reverse=True)


def reinforce_crystal(tag: str):
    """Boost a crystal's importance when it's mentioned again.

    Call this when semantic search or pattern matching finds
    a user message relates to an existing crystal.
    """
    crystals = []
    found = False
    try:
        with _crystal_lock:
            if os.path.exists(CRYSTAL_PATH):
                with open(CRYSTAL_PATH) as f:
                    for line in f:
                        try:
                            c = json.loads(line)
                            if c.get("tag") == tag:
                                # Weight boost by current salience
                                boost = 0.12  # base boost
                                try:
                                    from services.emotion.salience import get_salience
                                    s = get_salience()
                                    if s:
                                        boost += s.get("reward", 0) * 0.08
                                        boost += s.get("surprise", 0) * 0.05
                                except Exception:
                                    logger.warning("Operation failed", exc_info=True)
                                c["importance"] = min(1.0, c.get("importance", 0.5) + boost)
                                c["reinforcement_count"] = c.get("reinforcement_count", 1) + 1
                                archive_path = ARCHIVE_PATH
                                try:
                                    if os.path.exists(archive_path):
                                        with archive_lock:
                                            with open(archive_path) as af:
                                                c["last_reinforced"] = sum(1 for _ in af)
                                except Exception:
                                    logger.warning("Operation failed", exc_info=True)
                                found = True
                            crystals.append(c)
                        except Exception:
                            logger.warning("Operation failed", exc_info=True)

            if found:
                tmp = CRYSTAL_PATH + ".tmp"
                with open(tmp, "w") as f:
                    for c in crystals:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                shutil.move(tmp, CRYSTAL_PATH)
    except Exception:
        logger.warning("Operation failed", exc_info=True)


def get_crystal_context() -> str:
    """Return active crystal memories for prompt injection.

    Filters out dormant crystals (those decayed below threshold).
    Active crystals are sorted by current importance.
    """
    crystals = get_crystals()
    active = [c for c in crystals if not c.get("dormant", False)]
    if not active:
        return ""

    lines = ["## 用户反复提及的话题（已牢记）"]
    for c in active[:12]:
        imp = c.get("current_importance", 0.5)
        star = "*" * min(3, int(imp * 3))
        lines.append(f"- {c['tag']}：{c['crystal']} [{star}]")
    return "\n".join(lines)
