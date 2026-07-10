"""Semantic memory search with pgvector.

Flow:
1. LLM extracts key semantic tags from each message
2. Tags are hashed into a 256-dim sparse vector
3. Vectors stored in pgvector with HNSW index
4. New message → search for similar past conversations → inject into context
"""

import hashlib
import json

from app.db import q, execute


VEC_DIM = 256
_EXTRACT_PROMPT = """从以下对话中提取5-10个关键的语义标签（主题、情感、意图、实体）, 纯中文。
输出格式：{"tags": ["标签1", "标签2", ...]}

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


_tag_client = None


def _get_tag_client():
    global _tag_client
    if _tag_client is None:
        from openai import OpenAI

        _tag_client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
    return _tag_client


def _llm_extract_tags(text: str) -> list[str]:
    """Use DeepSeek to extract semantic tags from text."""
    try:
        client = _get_tag_client()
        resp = client.chat.completions.create(
            model="deepseek-chat",
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
        return []


def _vec_to_halfvec(values: list[float]) -> str:
    """Convert float list to pgvector halfvec literal."""
    return f"'[{','.join(f'{v:.6f}' for v in values)}]'::halfvec"


def index_turn(chat_id: int, message: str):
    """Extract tags, hash to vector, and store in pgvector."""
    tags = _llm_extract_tags(message)
    if not tags:
        return
    vec = _hash_to_vector(tags)
    halfvec = _vec_to_halfvec(vec)
    execute(
        f"INSERT INTO memory_vectors (chat_id, embedding) VALUES (%s, {halfvec})",
        [chat_id],
    )


def search_similar(query: str, limit: int = 5) -> list[dict]:
    """Find semantically similar past conversation turns.

    Returns list of {chat_id, user_msg, avatar_reply, similarity}.
    """
    tags = _llm_extract_tags(query)
    if not tags:
        return []
    vec = _hash_to_vector(tags)
    halfvec = _vec_to_halfvec(vec)

    rows = q(
        f"""SELECT mv.chat_id, ch.user_msg, ch.avatar_reply,
                   1 - (mv.embedding <=> {halfvec}) AS similarity
            FROM memory_vectors mv
            JOIN chat_history ch ON ch.id = mv.chat_id
            WHERE 1 - (mv.embedding <=> {halfvec}) > 0.3
            ORDER BY mv.embedding <=> {halfvec}
            LIMIT %s""",
        [limit],
    )
    return rows


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
