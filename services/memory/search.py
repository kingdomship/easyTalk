"""Semantic memory search with pgvector.

Flow:
1. LLM extracts key semantic tags from each message
2. Tags are hashed into a 256-dim sparse vector
3. Vectors stored in pgvector with HNSW index
4. New message → search for similar past conversations → inject into context
"""

import hashlib
import json
import logging

from app.db import q, execute

logger = logging.getLogger("emoji-chat")


VEC_DIM = 256
_EXTRACT_PROMPT = """从以下对话中提取5-10个关键的语义标签（主题、情感、意图、实体）, 纯中文。
以json格式输出：{"tags": ["标签1", "标签2", ...]}

示例：
"我今天好累啊，加班到很晚" → {"tags": ["工作", "疲惫", "加班", "倾诉", "负面情绪"]}
"哈哈这个笑话好好笑" → {"tags": ["笑话", "开心", "幽默", "正面情绪", "娱乐"]}"""



def _hash_to_vector(tags: list[str], dim: int = VEC_DIM) -> list[float]:
    """Hash semantic tags into a sparse float vector.

    Each tag maps to 3 positions via hashing. Related tags will overlap,
    giving semantic similarity in cosine space.
    """
    vec = [0.0] * dim
    for tag in tags:
        tag_bytes = tag.strip().lower().encode("utf-8")
        for seed in (0, 1, 2):
            h = hashlib.md5(tag_bytes + bytes([seed]))
            pos = int.from_bytes(h.digest()[:2], "big") % dim
            val = (int.from_bytes(h.digest()[:1], "big") / 255.0) * 2 - 1  # [-1, 1]
            vec[pos] += val
    # Normalize
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _llm_extract_tags(text: str) -> list[str]:
    """Use LLM to extract semantic tags from text."""
    from app.utils import get_llm, get_llm_model
    client = get_llm()
    if client is None:
        return []
    try:
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=200,
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("tags", [])
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return []




def index_turn(chat_id: int, message: str = "", tags: list[str] | None = None):
    """Extract tags (or reuse provided), hash to vector, and store in pgvector.

    When tags are provided (from the main LLM call), the separate
    _llm_extract_tags API call is skipped entirely.
    """
    if tags is None:
        tags = _llm_extract_tags(message)
    if not tags:
        return
    vec = _hash_to_vector(tags)
    e_json = json.dumps(vec)
    execute(
        "INSERT INTO memory_vectors (chat_id, embedding) VALUES (%s, %s::halfvec)",
        [chat_id, e_json],
    )


def search_similar(query: str, limit: int = 5, use_rerank: bool = True) -> list[dict]:
    """Find semantically similar past conversation turns.

    When use_rerank=True, fetches top-20 via cosine search then passes
    through cross-encoder reranker to select the best 5.

    Returns list of {chat_id, user_msg, avatar_reply, similarity}.
    """
    tags = _llm_extract_tags(query)
    if not tags:
        return []
    vec = _hash_to_vector(tags)
    e_json = json.dumps(vec)

    fetch_limit = 20 if use_rerank else limit
    rows = q(
        """SELECT mv.chat_id, ch.user_msg, ch.avatar_reply,
                   1 - (mv.embedding <=> %s::halfvec) AS similarity
            FROM memory_vectors mv
            JOIN chat_history ch ON ch.id = mv.chat_id
            WHERE 1 - (mv.embedding <=> %s::halfvec) > 0.3
            ORDER BY mv.embedding <=> %s::halfvec
            LIMIT %s""",
        [e_json, e_json, e_json, fetch_limit],
    )

    if use_rerank and len(rows) > limit:
        from services.memory.reranker import rerank_if_needed
        return rerank_if_needed(query, rows)

    return rows[:limit]


def build_memory_context(user_msg: str, limit: int = 5) -> str:
    """Search for relevant memories and format as context for the system prompt.

    Returns empty string if no relevant memories found.
    """
    results = search_similar(user_msg, limit)
    if not results:
        return ""

    lines = ["## 相关的过往回忆（可在对话中自然提及）："]
    for r in results:
        lines.append(f"- 用户曾说过：「{r['user_msg'][:80]}」→ 你回复：「{r['avatar_reply'][:60]}」")
    return "\n".join(lines)
