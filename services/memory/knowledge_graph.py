"""Temporal knowledge graph — entity/relationship tracking with time awareness.

Tracks entities mentioned by the user and the user's evolving attitude toward
them. Answers questions like "what does the user think about X?" and
"how has their opinion changed over time?"

LLM extraction runs every ~20 turns in background. All storage in PostgreSQL
(kg_entities + kg_relationships tables), no external graph DB needed.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

from app.db import q, execute
from app.utils import get_llm_model

logger = logging.getLogger("emoji-chat")

_KG_EXTRACT_EVERY = 20
_kg_lock = threading.Lock()
_last_kg_count = 0

_USER_ENTITY_ID = None

_EXTRACT_PROMPT = """从用户消息中提取实体和用户对这些实体的态度/关系，输出JSON数组。

实体类型: person(人物), place(地点), food(食物), activity(活动), work(工作), hobby(爱好), media(影视/音乐/书籍), tech(技术), other(其他)

关系类型: likes(喜欢), dislikes(不喜欢), loves(热爱), hates(讨厌), prefers(偏好), works_at(工作在), studies(学习), owns(拥有), wants(想要), visited(去过)

示例:
用户说"我最近很喜欢看《三体》，但是越来越讨厌加班了"
输出: [
  {"entity": "三体", "type": "media", "relation": "likes", "confidence": 0.9},
  {"entity": "加班", "type": "work", "relation": "dislikes", "confidence": 0.8}
]

只输出JSON数组，不要其他内容。"""


def _get_user_entity_id() -> int:
    global _USER_ENTITY_ID
    if _USER_ENTITY_ID is not None:
        return _USER_ENTITY_ID
    row = q("SELECT id FROM kg_entities WHERE name = '__用户__' AND type = 'person'", fetch="one")
    if row:
        _USER_ENTITY_ID = row["id"]
    else:
        execute("INSERT INTO kg_entities (name, type) VALUES ('__用户__', 'person')")
        row = q("SELECT id FROM kg_entities WHERE name = '__用户__' AND type = 'person'", fetch="one")
        _USER_ENTITY_ID = row["id"] if row else 1
    return _USER_ENTITY_ID


def _get_llm():
    from app.utils import get_llm, get_llm_model
    return get_llm()


def upsert_entity(name: str, etype: str = "other", metadata: dict | None = None) -> int:
    """Insert or update an entity, return its ID."""
    existing = q(
        "SELECT id, metadata FROM kg_entities WHERE name = %s AND type = %s",
        [name, etype], fetch="one",
    )
    if existing:
        merged_meta = dict(existing.get("metadata") or {})
        if metadata:
            merged_meta.update(metadata)
        execute(
            "UPDATE kg_entities SET last_seen = NOW(), metadata = %s WHERE id = %s",
            [json.dumps(merged_meta, ensure_ascii=False), existing["id"]],
        )
        return existing["id"]
    execute(
        "INSERT INTO kg_entities (name, type, metadata) VALUES (%s, %s, %s)",
        [name, etype, json.dumps(metadata or {}, ensure_ascii=False)],
    )
    row = q("SELECT id FROM kg_entities WHERE name = %s AND type = %s", [name, etype], fetch="one")
    return row["id"] if row else 0


def add_relationship(entity_id: int, relation: str, strength: float = 0.5):
    """Add a user→entity relationship, invalidating any prior relation of the same type."""
    user_id = _get_user_entity_id()
    # Invalidate any existing active relationship of same type for this entity
    execute(
        "UPDATE kg_relationships SET invalid_at = NOW() "
        "WHERE source_id = %s AND target_id = %s AND relation = %s AND invalid_at IS NULL",
        [user_id, entity_id, relation],
    )
    execute(
        "INSERT INTO kg_relationships (source_id, target_id, relation, strength) "
        "VALUES (%s, %s, %s, %s)",
        [user_id, entity_id, relation, round(strength, 4)],
    )


def extract_from_message(msg: str) -> list[dict]:
    """Extract entities and relationships from a user message via LLM.

    Returns list of {entity, type, relation, confidence}.
    """
    if len(msg) < 10:
        return []
    try:
        client = _get_llm()
        if client is None:
            return []
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content
        # Handle both array and object wrapping
        data = json.loads(raw)
        if isinstance(data, dict):
            items = data.get("entities", data.get("items", []))
        elif isinstance(data, list):
            items = data
        else:
            return []
        return [
            {
                "entity": str(item.get("entity", "")),
                "type": str(item.get("type", "other")),
                "relation": str(item.get("relation", "mentioned")),
                "confidence": float(item.get("confidence", 0.5)),
            }
            for item in items
            if item.get("entity")
        ][:10]
    except Exception:
        logger.warning("KG extraction failed", exc_info=True)
        return []


def process_message(msg: str):
    """Extract entities from a message and update the knowledge graph.

    Called in background after each user message.
    """
    items = extract_from_message(msg)
    for item in items:
        try:
            eid = upsert_entity(item["entity"], item["type"])
            if eid:
                add_relationship(eid, item["relation"], item["confidence"])
        except Exception:
            logger.warning("KG process item failed", exc_info=True)


def maybe_extract_kg(msg: str):
    """Trigger KG extraction every _KG_EXTRACT_EVERY turns.

    Called from chat route after each reply.
    """
    global _last_kg_count
    if not _kg_lock.acquire(blocking=False):
        return
    try:
        row = q("SELECT COUNT(*) AS cnt FROM chat_history", fetch="one")
        count = row["cnt"] if row else 0
        if count - _last_kg_count < _KG_EXTRACT_EVERY:
            return
        _last_kg_count = count
        process_message(msg)
    except Exception:
        logger.warning("KG periodic extraction failed", exc_info=True)
    finally:
        _kg_lock.release()


# ── Temporal queries ──────────────────────────────────────────────────

def get_temporal_insight() -> str:
    """Detect attitude changes over time.

    Finds entities where the user's relationship changed significantly,
    e.g. "liked X last month but now dislikes it."
    """
    rows = q("""
        SELECT e.name, e.type,
               r_old.relation AS old_rel, r_old.valid_at AS old_since,
               r_new.relation AS new_rel, r_new.valid_at AS new_since
        FROM kg_relationships r_new
        JOIN kg_entities e ON e.id = r_new.target_id
        JOIN kg_relationships r_old ON r_old.target_id = r_new.target_id
          AND r_old.relation != r_new.relation
          AND r_old.invalid_at IS NOT NULL
        WHERE r_new.invalid_at IS NULL
          AND r_new.source_id = %s
          AND r_old.source_id = %s
          AND r_old.valid_at < NOW() - INTERVAL '3 days'
        ORDER BY r_new.valid_at DESC
        LIMIT 5
    """, [_get_user_entity_id(), _get_user_entity_id()])
    if not rows:
        return ""

    lines = ["## 用户态度变化（可在对话中自然体现你的觉察）："]
    relation_cn = {
        "likes": "喜欢", "dislikes": "不喜欢", "loves": "热爱", "hates": "讨厌",
        "prefers": "偏好", "wants": "想要",
    }
    for r in rows:
        old_cn = relation_cn.get(r["old_rel"], r["old_rel"])
        new_cn = relation_cn.get(r["new_rel"], r["new_rel"])
        lines.append(f"- {r['name']}：以前{old_cn} → 现在{new_cn}")
    return "\n".join(lines)


def get_entity_history(name: str) -> list[dict]:
    """Get the full relationship history for a specific entity."""
    user_id = _get_user_entity_id()
    return q(
        "SELECT r.relation, r.strength, r.valid_at, r.invalid_at "
        "FROM kg_relationships r "
        "JOIN kg_entities e ON e.id = r.target_id "
        "WHERE e.name = %s AND r.source_id = %s "
        "ORDER BY r.valid_at DESC",
        [name, user_id],
    )


def get_current_state() -> list[dict]:
    """Get all currently valid (active) relationships."""
    user_id = _get_user_entity_id()
    return q(
        "SELECT e.name, e.type, r.relation, r.strength, r.valid_at "
        "FROM kg_relationships r "
        "JOIN kg_entities e ON e.id = r.target_id "
        "WHERE r.source_id = %s AND r.invalid_at IS NULL "
        "ORDER BY r.valid_at DESC "
        "LIMIT 30",
        [user_id],
    )


def get_knowledge_graph_context() -> str:
    """Build KG context for injection into the system prompt.

    Returns temporal insights and current entity summary.
    """
    parts = []

    temporal = get_temporal_insight()
    if temporal:
        parts.append(temporal)

    state = get_current_state()
    if state:
        lines = ["## 用户当前的偏好/状态（已知）："]
        for s in state[:10]:
            relation_cn = {
                "likes": "喜欢", "dislikes": "不喜欢", "loves": "热爱", "hates": "讨厌",
                "prefers": "偏好", "works_at": "工作在", "studies": "在学习",
                "owns": "拥有", "wants": "想要", "visited": "去过",
            }
            rel = relation_cn.get(s["relation"], s["relation"])
            lines.append(f"- {rel}{s['name']}（{s['type']}）")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) if parts else ""
