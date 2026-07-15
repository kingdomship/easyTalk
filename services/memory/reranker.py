"""Cross-encoder reranker — two-stage memory retrieval.

Stage 1 (fast, free): existing hash-vector cosine search → top-20 candidates.
Stage 2 (rerank, on-demand): DeepSeek LLM reranks top-20 → top-5.
Only triggers when Stage 1 confidence is low.

This avoids adding a local cross-encoder model (~500MB) to the Docker image
by reusing the existing DeepSeek API for reranking.
"""

import hashlib
import json
import logging
import time

logger = logging.getLogger("emoji-chat")

# Simple in-memory cache: query_hash → (timestamp, results)
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 300  # 5 minutes
_MAX_CACHE_SIZE = 200

_RERANK_PROMPT = """你是一个记忆相关性排序助手。判断以下历史对话片段与用户当前消息的相关性。

用户当前消息：{query}

候选记忆：
{candidates}

请判断每条候选记忆与当前消息的语义相关性。按相关度从高到低排列，输出JSON格式：
{{"ranked_indices": [3, 1, 5, 2, 4], "reason": "简短说明排序理由"}}

其中ranked_indices是候选编号（从1开始），仅包含确实相关的候选。
如果某条完全无关，就不要包含它。

只输出JSON，不要其他内容。"""


def compute_confidence(candidates: list[dict]) -> float:
    """Heuristic confidence score for Stage 1 results.

    Returns [0, 1] where >0.7 means "good enough, skip rerank".
    """
    if not candidates:
        return 0.0

    top_score = float(candidates[0].get("similarity", 0))
    if top_score < 0.4:
        return top_score  # Low ceiling → always rerank

    # Clear winner: big gap between #1 and #2 with high top score
    if len(candidates) > 1:
        gap = top_score - float(candidates[1].get("similarity", 0))
        if gap > 0.15 and top_score > 0.6:
            return 0.85

    # Coverage: how many results we got vs requested
    coverage = min(1.0, len(candidates) / 5.0)
    return top_score * 0.6 + coverage * 0.4


def _cache_key(query: str, candidates: list[dict]) -> str:
    """Derive a cache key from the query and candidate IDs."""
    ids = sorted(str(c.get("chat_id", "")) for c in candidates)
    raw = query + "|" + ",".join(ids)
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cache_get(key: str) -> list[dict] | None:
    """Check cache, evict expired entries."""
    now = time.time()
    if key in _cache:
        ts, results = _cache[key]
        if now - ts < _CACHE_TTL:
            return results
        del _cache[key]
    # Evict oldest if too large
    if len(_cache) > _MAX_CACHE_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest]
    return None


def _cache_set(key: str, results: list[dict]):
    _cache[key] = (time.time(), results)


def llm_rerank(query: str, candidates: list[dict]) -> list[dict]:
    """Use DeepSeek to rerank candidates by relevance to query.

    Returns candidates reordered by LLM relevance judgment.
    """
    if len(candidates) <= 5:
        return candidates

    # Build candidate list for the LLM
    cand_lines = []
    for i, c in enumerate(candidates, 1):
        user = c.get("user_msg", "")[:100]
        cand_lines.append(f"[{i}] 用户: {user}")

    try:
        from app.utils import get_llm
        client = get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _RERANK_PROMPT.format(
                    query=query,
                    candidates="\n".join(cand_lines),
                )},
                {"role": "user", "content": "请按相关度排序。"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            indices = data.get("ranked_indices", [])
            # Reorder candidates by LLM ranking
            idx_set = set(indices)
            reranked = [candidates[i - 1] for i in indices if 1 <= i <= len(candidates)]
            # Append any candidates the LLM dropped
            for i, c in enumerate(candidates, 1):
                if i not in idx_set:
                    reranked.append(c)
            return reranked[:5]
    except Exception:
        logger.warning("LLM rerank failed, returning original order", exc_info=True)

    return candidates[:5]


def rerank_if_needed(query: str, candidates: list[dict],
                     force_rerank: bool = False) -> list[dict]:
    """Two-stage retrieval with optional reranking.

    Returns top-5 most relevant candidates.
    """
    if not candidates:
        return []

    if not force_rerank:
        confidence = compute_confidence(candidates)
        if confidence > 0.7:
            return candidates[:5]

    # Check cache
    ck = _cache_key(query, candidates)
    cached = _cache_get(ck)
    if cached:
        return cached

    reranked = llm_rerank(query, candidates)
    _cache_set(ck, reranked)
    return reranked
