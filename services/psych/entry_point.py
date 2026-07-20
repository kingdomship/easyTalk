"""Curiosity-powered entry point detection.

Manages a lightweight queue of things the AI naturally wants to learn about
the user. Complements the knowledge graph (which tracks what we KNOW) by
tracking what we WANT TO KNOW.

Seeds come from:
- KG entity gaps (user mentioned a hobby but didn't elaborate)
- Life domain transitions (new domain suddenly becomes salient)
- Topic shifts (user abruptly changes topic — possible avoidance/deflection)

Designed to make the AI feel curious and attentive, not interrogative.
"""

import json
import logging
import os
import random
import threading

from app.config import CURIOSITY_PATH

logger = logging.getLogger("emoji-chat")

_MAX_QUEUE_SIZE = 5
_MIN_TURNS_BETWEEN_ASK = 20  # Don't ask the same thing within 20 turns

_lock = threading.Lock()


# ── Persistence ─────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    if os.path.exists(CURIOSITY_PATH):
        try:
            with open(CURIOSITY_PATH) as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to load curiosity queue", exc_info=True)
    return []


def _save(items: list[dict]):
    try:
        from app.config import atomic_write
        atomic_write(CURIOSITY_PATH, json.dumps(items, ensure_ascii=False, indent=2))
    except Exception:
        logger.warning("Failed to save curiosity queue", exc_info=True)


# ── Seed detection ──────────────────────────────────────────────────────────

# Pattern: user mentions something specific but doesn't elaborate
# e.g. "今天去拍了几张照片" → curiosity: what kind of photography?
_VAGUE_HOOKS = [
    ("去了", "什么地方"),
    ("吃了", "什么"),
    ("学了", "学什么"),
    ("买了", "什么样的"),
    ("看了", "感觉怎么样"),
    ("玩了", "好不好玩"),
    ("做了", "什么样的"),
]


def _detect_info_gaps(msg: str) -> list[str]:
    """Detect messages where the user mentions an activity without elaborating."""
    gaps = []
    for trigger, _ in _VAGUE_HOOKS:
        idx = msg.find(trigger)
        if idx >= 0:
            # Extract the rest of the sentence after trigger
            rest = msg[idx + len(trigger):]
            if len(rest) < 15:
                gaps.append(msg[idx:idx + 30])
    return gaps


def seed_from_message(msg: str, turn_count: int):
    """Seed curiosity items from a single user message (heuristic, zero LLM)."""
    gaps = _detect_info_gaps(msg)
    if not gaps:
        return

    with _lock:
        queue = _load()
        existing = {item.get("hook", "") for item in queue}
        for gap in gaps:
            if gap in existing:
                continue
            if len(queue) >= _MAX_QUEUE_SIZE:
                queue.pop(0)
            queue.append({
                "hook": gap,
                "question": f"用户提到了「{gap[:40]}」，可以自然地多问一句",
                "asked_count": 0,
                "last_asked_turn": None,
                "created_at_turn": turn_count,
            })
        _save(queue)


# ── LLM enrichment (call periodically, e.g. with attachment analysis) ──────

def enrich_with_llm(recent_transcript: str):
    """Use LLM to generate curiosity items from recent conversation.

    Called every ~30 turns alongside attachment style analysis.
    """
    from app.utils import get_llm, get_llm_model

    client = get_llm()
    if client is None:
        return

    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": (
                    "你正在阅读一段用户和AI的对话。请找出用户提到过但没有深入聊的话题——"
                    "也就是AI自然想知道但还没问的事情。\n\n"
                    "要求：\n"
                    "- 最多列出3个\n"
                    "- 必须是对话中用户确实提过的\n"
                    "- 不能是已经详细聊过的话题\n"
                    "- 问题要自然，像朋友间的好奇，不审问\n"
                    "- 用JSON格式输出：{\"items\": [{\"hook\": \"用户原始原话片段\", \"question\": \"AI可以怎么自然地追问\"}]}"
                )},
                {"role": "user", "content": recent_transcript},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content
        # Parse JSON (may be wrapped in markdown code block)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        items = data.get("items", [])

        with _lock:
            queue = _load()
            existing = {item.get("hook", "") for item in queue}
            for item in items:
                hook = item.get("hook", "")
                if hook and hook not in existing:
                    if len(queue) >= _MAX_QUEUE_SIZE:
                        queue.pop(0)
                    queue.append({
                        "hook": hook,
                        "question": item.get("question", ""),
                        "asked_count": 0,
                        "last_asked_turn": None,
                    })
            _save(queue)
    except Exception:
        logger.warning("Curiosity LLM enrichment failed", exc_info=True)


# ── Mark as asked ───────────────────────────────────────────────────────────

def mark_asked(hook: str, turn_count: int):
    """Mark a curiosity item as having been asked (so we don't repeat)."""
    with _lock:
        queue = _load()
        for item in queue:
            if item.get("hook") == hook:
                item["asked_count"] = item.get("asked_count", 0) + 1
                item["last_asked_turn"] = turn_count
                if item["asked_count"] >= 2:
                    queue.remove(item)
                break
        _save(queue)


# ── Context injection ───────────────────────────────────────────────────────

def get_curiosity_hint(turn_count: int = 0) -> str | None:
    """Return a single curiosity hint for system prompt injection.

    Picks the most natural-feeling item from the queue, avoiding recently-asked ones.
    Returns None if queue is empty or all items have been asked recently.
    """
    with _lock:
        queue = _load()

    if not queue:
        return None

    # Filter: skip items asked within the last _MIN_TURNS_BETWEEN_ASK turns
    available = [
        item for item in queue
        if item.get("last_asked_turn") is None
        or (turn_count - item["last_asked_turn"]) >= _MIN_TURNS_BETWEEN_ASK
    ]
    if not available:
        return None

    # Pick one randomly for variety
    item = random.choice(available)
    return (
        f"[自然好奇] {item['question']}\n"
        f"（你心里有数就好，不要强行追问。时机合适、话头自然的时候再轻轻带一句。）"
    )


# ── Update function for the pipeline ────────────────────────────────────────

def update_curiosity_queue(msg: str, turn_count: int = 0):
    """Lightweight heuristic seeding from a single message.

    Call this every turn from _post_reply_pipeline.
    The LLM-based enrichment is called separately on a longer cycle.
    """
    seed_from_message(msg, turn_count)
