"""Narrative distillation — layered memory from turns to stories.

Inspired by psyche-rs: Instants -> Situations -> Episodes -> Narratives.

- Situation: a coherent topic segment spanning multiple turns, detected
  by LLM analyzing conversation for topic boundaries.
- Episode: a meaningful event composed of multiple situations, distilled
  by LLM into a short story paragraph.
- Narrative: the overarching relationship story, fed into the existing
  conversation_summary during condense cycles.

This gives the AI structural memory — it can reference past events as
"stories" rather than just keyword-matched fragments.
"""

import json
import logging
import os
import threading

logger = logging.getLogger("emoji-chat")

from app.config import ARCHIVE_PATH, EPISODES_PATH, SITUATIONS_PATH

_SITUATIONS_PATH = SITUATIONS_PATH
_EPISODES_PATH = EPISODES_PATH

_SITUATION_CHECK_EVERY = 10
_EPISODE_CHECK_THRESHOLD = 5  # min situations before distilling episode

_situation_lock = threading.Lock()
_episode_lock = threading.Lock()
_last_situation_check = 0
_last_episode_check = 0

_SITUATION_PROMPT = """你是一个对话分析助手。分析以下对话记录，识别话题的切换点。

规则：
1. 将对话按话题分割成"场景"（situation），每个场景是一个连续的话题单元
2. 每个场景至少包含3轮对话（用户+AI各算一轮）
3. 两个场景之间有明显的话题切换（例如从聊工作切换到聊音乐）
4. 每个场景给出：标题(5-10字)、一句话摘要(20-40字)
5. 如果整个对话是同一条主线，那就只输出一个场景

输出JSON数组：
[{"title": "场景标题", "summary": "一句话摘要", "start_idx": 起始行号, "end_idx": 结束行号}]

行号从1开始，对应输入中"- "开头的每一条消息。
只输出JSON，不要其他内容。"""

_EPISODE_PROMPT = """你是一个故事叙述助手。以下是最近对话中的几个场景片段：

{situations_text}

请将这些场景编织成一个简短的"情节"（episode），用一段话（100-150字）讲述：
- 这些场景之间有什么联系？
- 体现了用户怎样的状态或变化？
- 你和用户之间形成了什么新的默契或理解？

用第一人称（"我"指AI），语气温暖自然。
直接输出情节文本，不要JSON。"""


def _count_archive_lines() -> int:
    path = ARCHIVE_PATH
    try:
        if os.path.exists(path):
            with open(path) as f:
                return sum(1 for _ in f)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return 0


def _load_archive_range(start: int, count: int) -> list[dict]:
    """Load a range of turns from conversation archive."""
    path = ARCHIVE_PATH
    turns = []
    try:
        if os.path.exists(path):
            with open(path) as f:
                lines = f.readlines()
            for line in lines[start:start + count]:
                try:
                    rec = json.loads(line)
                    if rec.get("user") or rec.get("assistant"):
                        turns.append(rec)
                except Exception:
                    logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return turns


def _load_existing_situations() -> list[dict]:
    situations = []
    try:
        if os.path.exists(_SITUATIONS_PATH):
            with open(_SITUATIONS_PATH) as f:
                for line in f:
                    try:
                        situations.append(json.loads(line))
                    except Exception:
                        logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return situations


def _save_situations(situations: list[dict]):
    os.makedirs(os.path.dirname(_SITUATIONS_PATH), exist_ok=True)
    try:
        with open(_SITUATIONS_PATH, "a") as f:
            for s in situations:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Operation failed", exc_info=True)


def detect_situations():
    """Analyze recent conversation to detect topic segments.

    Runs every _SITUATION_CHECK_EVERY turns. Uses LLM to find topic
    boundaries and stores situation records.
    """
    global _last_situation_check
    if not _situation_lock.acquire(blocking=False):
        return
    try:
        total = _count_archive_lines()
        if total - _last_situation_check < _SITUATION_CHECK_EVERY:
            return
        _last_situation_check = total

        # Check how many turns we've already analyzed
        existing = _load_existing_situations()
        last_end = 0
        for s in existing:
            last_end = max(last_end, s.get("end_line", 0))

        # Load new turns since last analysis
        new_turns = _load_archive_range(last_end, 40)
        if len(new_turns) < 6:
            return

        # Build numbered transcript
        numbered = []
        for i, t in enumerate(new_turns, start=1):
            u = t.get("user", "")
            a = t.get("assistant", "")
            if u:
                numbered.append(f"- 用户：{u[:80]}")
            if a:
                numbered.append(f"- AI：{a[:80]}")

        if len(numbered) < 6:
            return

        from app.utils import get_llm
        client = get_llm()

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": _SITUATION_PROMPT},
                    {"role": "user", "content": "\n".join(numbered)},
                ],
                temperature=0.4,
                max_tokens=500,
            )
            raw = resp.choices[0].message.content.strip()
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                return
            parsed = json.loads(raw[start:end])
        except Exception:
            logger.warning("Operation failed", exc_info=True)
            return

        if not isinstance(parsed, list):
            return

        new_situations = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            summary = item.get("summary", "")
            start_idx = item.get("start_idx", 0)
            end_idx = item.get("end_idx", 0)
            if not title or not summary:
                continue
            new_situations.append({
                "title": title,
                "summary": summary,
                "start_line": last_end + start_idx,
                "end_line": last_end + end_idx,
                "turn_count": end_idx - start_idx + 1,
            })

        if new_situations:
            _save_situations(new_situations)
            logger.info("Detected %d situations: %s",
                         len(new_situations),
                         [s["title"] for s in new_situations])
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    finally:
        _situation_lock.release()


def _load_existing_episodes() -> list[dict]:
    episodes = []
    try:
        if os.path.exists(_EPISODES_PATH):
            with open(_EPISODES_PATH) as f:
                for line in f:
                    try:
                        episodes.append(json.loads(line))
                    except Exception:
                        logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    return episodes


def distill_episode():
    """Distill recent situations into a narrative episode.

    Runs when 5+ new situations accumulate. Uses LLM to weave them
    into a coherent story paragraph.
    """
    global _last_episode_check
    if not _episode_lock.acquire(blocking=False):
        return
    try:
        situations = _load_existing_situations()
        episodes = _load_existing_episodes()

        # Count how many situations have been covered by existing episodes
        covered = set()
        for ep in episodes:
            for sid in ep.get("situation_ids", []):
                covered.add(sid)

        new_situations = [
            s for i, s in enumerate(situations)
            if str(i) not in covered
        ]

        if len(new_situations) < _EPISODE_CHECK_THRESHOLD:
            return

        # Only process if we haven't checked recently
        if len(new_situations) - _last_episode_check < _EPISODE_CHECK_THRESHOLD:
            return
        _last_episode_check = len(new_situations)

        # Build situation text for the LLM
        sit_text = "\n".join(
            f"- {s['title']}：{s['summary']}"
            for s in new_situations[-8:]  # take last 8 at most
        )

        from app.utils import get_llm
        client = get_llm()

        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": _EPISODE_PROMPT.format(
                        situations_text=sit_text,
                    )},
                    {"role": "user", "content": "请编织这些场景。"},
                ],
                temperature=0.6,
                max_tokens=300,
            )
            narrative = resp.choices[0].message.content.strip()
        except Exception:
            logger.warning("Operation failed", exc_info=True)
            return

        if not narrative or len(narrative) < 20:
            return

        episode = {
            "narrative": narrative,
            "situation_ids": [
                str(len(situations) - len(new_situations) + i)
                for i in range(min(8, len(new_situations)))
            ],
            "situation_count": len(new_situations),
        }

        os.makedirs(os.path.dirname(_EPISODES_PATH), exist_ok=True)
        try:
            with open(_EPISODES_PATH, "a") as f:
                f.write(json.dumps(episode, ensure_ascii=False) + "\n")
            logger.info("Distilled episode: %s...", narrative[:60])
        except Exception:
            logger.warning("Operation failed", exc_info=True)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
    finally:
        _episode_lock.release()


def get_narrative_context() -> str:
    """Return narrative context for prompt injection.

    Includes recent situations and episodes for structural memory.
    Called during _build_context().
    """
    situations = _load_existing_situations()
    episodes = _load_existing_episodes()

    parts = []

    # Recent situations (last 3)
    if situations:
        recent = situations[-3:]
        lines = ["## 最近的对话场景"]
        for s in recent:
            lines.append(f"- {s['title']}：{s['summary']}")
        parts.append("\n".join(lines))

    # Recent episodes (last 2)
    if episodes:
        recent_ep = episodes[-2:]
        lines = ["## 关系故事线"]
        for ep in recent_ep:
            lines.append(f"- {ep['narrative'][:150]}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def get_situations() -> list[dict]:
    """Return all detected situations (for API/debugging)."""
    return _load_existing_situations()


def get_episodes() -> list[dict]:
    """Return all distilled episodes (for API/debugging)."""
    return _load_existing_episodes()
