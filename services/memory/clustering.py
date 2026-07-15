"""Memory constellation builder — clusters memories into topic galaxies.

Provides data for the frontend Canvas star map visualization.
Each "galaxy" is a topic cluster; "stars" are individual crystal memories
with position, size, and importance derived from the memory system.
"""

import json
import logging
import math
import os
import random

from app.db import q

logger = logging.getLogger("emoji-chat")

GALAXY_TOPICS = {
    "social":   {"label": "社交",   "color": "#ff6b9d", "angle": 0.0,
                 "keywords": ["朋友", "家人", "同事", "同学", "社交", "聚会", "聊天", "认识", "关系"]},
    "places":   {"label": "地点",   "color": "#4ecdc4", "angle": 1.2566,
                 "keywords": ["去过", "旅行", "城市", "地方", "家", "公司", "学校", "餐厅", "公园"]},
    "events":   {"label": "事件",   "color": "#ffd93d", "angle": 2.5133,
                 "keywords": ["发生", "经历", "那天", "时候", "事件", "记得", "以前", "上次"]},
    "hobbies":  {"label": "爱好",   "color": "#6c5ce7", "angle": 3.7699,
                 "keywords": ["喜欢", "爱好", "游戏", "音乐", "电影", "看书", "运动", "画画", "唱歌"]},
    "projects": {"label": "项目",   "color": "#00b894", "angle": 5.0265,
                 "keywords": ["工作", "项目", "学习", "考试", "面试", "任务", "计划", "目标", "代码"]},
}


def _classify_topic(text: str) -> str:
    """Classify a memory text into one of the 5 galaxy topics."""
    text_lower = text.lower()
    scores = {}
    for topic, info in GALAXY_TOPICS.items():
        score = sum(1 for kw in info["keywords"] if kw in text_lower)
        scores[topic] = score
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "events"


def _star_position(galaxy_angle: float, index: int, total: int) -> tuple[float, float]:
    """Compute a star's position within its galaxy's elliptical orbit.

    Galaxies orbit at radius ~200px from center. Stars scatter within
    the galaxy with a spread of ~60px.
    """
    rng = random.Random(index * 137 + hash(str(galaxy_angle)) % 1000)
    orbit_r = 180 + rng.uniform(-30, 30)
    scatter_r = rng.uniform(10, 55)
    scatter_angle = rng.uniform(0, 2 * math.pi)
    center_x = math.cos(galaxy_angle) * orbit_r
    center_y = math.sin(galaxy_angle) * orbit_r
    return (
        round(center_x + math.cos(scatter_angle) * scatter_r, 1),
        round(center_y + math.sin(scatter_angle) * scatter_r, 1),
    )


def _merge_by_topic(memories: list) -> list:
    """Merge memories that share significant keyword overlap into topic clusters.

    Each cluster becomes a single star, with merged importance and best summary.
    """
    if len(memories) <= 1:
        return memories

    # Extract key terms (2+ char Chinese phrases) from each memory
    def _key_terms(text):
        terms = set()
        for i in range(len(text) - 1):
            chunk = text[i:i + 2]
            # Keep only meaningful Chinese character pairs
            if all('一' <= c <= '鿿' or c.isalpha() for c in chunk):
                terms.add(chunk)
        return terms

    # Build term sets for each memory
    term_sets = [_key_terms(m["content"]) for m in memories]

    # Union-find to group overlapping memories
    parent = list(range(len(memories)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(memories)):
        for j in range(i + 1, len(memories)):
            si, sj = term_sets[i], term_sets[j]
            if not si or not sj:
                continue
            # Jaccard similarity: overlap / union
            overlap = len(si & sj)
            if overlap >= 3 or (overlap >= 2 and overlap / min(len(si), len(sj)) > 0.3):
                union(i, j)

    # Merge each group
    groups = {}
    for i, mem in enumerate(memories):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(mem)

    merged = []
    next_id = 90000
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
        else:
            # Pick the longest content as representative
            best = max(group, key=lambda m: len(m["content"]))
            combined_importance = min(1.0, sum(m["importance"] for m in group))
            merged.append({
                "id": next_id,
                "content": best["content"][:100],
                "importance": combined_importance,
                "use_count": sum(m["use_count"] for m in group),
            })
            next_id += 1

    return merged


def build_constellation() -> dict:
    """Build the full constellation data structure for frontend rendering.

    Returns:
        {core: {user: {label, color}, ai: {label, color}},
         galaxies: [{topic, label, color, angle, stars: [{id, tag, summary, x, y, size, importance}]}],
         connections: [{from_id, to_id}]}
    """
    # Load crystal memories
    rows = q(
        "SELECT id, reply AS content, "
        "LEAST(1.0, use_count::real / 20.0) AS importance, "
        "use_count, created_at "
        "FROM emotion_cache WHERE sequence_data IS NOT NULL OR use_count > 2 "
        "ORDER BY use_count DESC LIMIT 50"
    )
    # Also load from narrative crystals if available
    crystal_rows = q(
        "SELECT id, insight AS content, 0.5 AS importance, 1 AS use_count, created_at "
        "FROM system2_insights WHERE category = 'general' LIMIT 20"
    )

    all_memories = []
    seen_hashes = set()

    def _add_memory(mem_id, content, importance, use_count):
        """Deduplicate by content hash before adding."""
        key = hash(content[:80])
        if key in seen_hashes:
            return
        seen_hashes.add(key)
        all_memories.append({
            "id": mem_id,
            "content": content,
            "importance": float(importance),
            "use_count": int(use_count),
        })

    for r in rows:
        content = (r.get("content") or r.get("reply") or "")[:100]
        if content:
            _add_memory(r["id"], content,
                        r.get("importance", 0.5),
                        r.get("use_count", 1))
    for r in crystal_rows:
        content = (r.get("content") or "")[:100]
        if content:
            _add_memory(r["id"] + 10000, content,
                        r.get("importance", 0.3),
                        r.get("use_count", 1))

    if not all_memories:
        # Fallback: build from emotion cache
        fallback = q(
            "SELECT id, reply, use_count FROM emotion_cache "
            "WHERE reply != '' ORDER BY use_count DESC LIMIT 30"
        )
        for r in fallback:
            content = r["reply"][:80]
            if content:
                _add_memory(r["id"], content,
                            min(1.0, int(r.get("use_count", 1)) / 20),
                            r.get("use_count", 1))

    # ── Topic aggregation: merge similar memories into single stars ──
    merged = _merge_by_topic(all_memories)

    # Classify into galaxies
    galaxies_data = {}
    for mem in merged:
        topic = _classify_topic(mem["content"])
        if topic not in galaxies_data:
            galaxies_data[topic] = []
        galaxies_data[topic].append(mem)

    # Build galaxy structures
    galaxies = []
    for topic, info in GALAXY_TOPICS.items():
        stars_data = galaxies_data.get(topic, [])
        stars = []
        for i, mem in enumerate(stars_data[:15]):
            x, y = _star_position(info["angle"], i, len(stars_data))
            size = max(2.0, min(8.0, 3 + mem["importance"] * 5))
            # Extract a short tag from content
            tag = mem["content"][:12].strip()
            if len(mem["content"]) > 12:
                tag += "..."
            stars.append({
                "id": mem["id"],
                "tag": tag,
                "summary": mem["content"][:50],
                "x": x,
                "y": y,
                "size": round(size, 1),
                "importance": round(mem["importance"], 2),
            })

        galaxies.append({
            "topic": topic,
            "label": info["label"],
            "color": info["color"],
            "angle": info["angle"],
            "star_count": len(stars),
            "stars": stars,
        })

    # Build connections between related stars (same topic + high importance)
    connections = []
    for galaxy in galaxies:
        important_stars = [s for s in galaxy["stars"] if s["importance"] > 0.4]
        for i in range(len(important_stars)):
            for j in range(i + 1, min(i + 3, len(important_stars))):
                connections.append({
                    "from_id": important_stars[i]["id"],
                    "to_id": important_stars[j]["id"],
                })

    # Load persona for core labels
    user_label = "我"
    ai_label = "AI"
    try:
        from app.config import PERSONA_PATH, PROFILE_PATH
        # Extract AI label from persona: look for "身份" in the role section
        if os.path.exists(PERSONA_PATH):
            with open(PERSONA_PATH) as f:
                in_frontmatter = False
                fallback_label = None
                for line in f:
                    stripped = line.strip()
                    if stripped == "---":
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter:
                        continue
                    if "名字" in stripped:
                        # "- 名字：陆薇" → "陆薇"
                        ai_label = stripped.split("：", 1)[-1].strip()[:8]
                        break
                    if "身份" in stripped:
                        # "- 身份：风趣、幽默、知性的漂亮女性" → "风趣幽默"
                        role = stripped.split("：", 1)[-1].split("、")
                        ai_label = "".join(role[:2])[:8]
                        break
                    if stripped.startswith("#") and fallback_label is None:
                        fallback_label = stripped.lstrip("#").strip()[:8]
                else:
                    if fallback_label:
                        ai_label = fallback_label
        # Try to find user's name from profile
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH) as f:
                in_frontmatter = False
                for line in f:
                    stripped = line.strip()
                    if stripped == "---":
                        in_frontmatter = not in_frontmatter
                        continue
                    if in_frontmatter:
                        continue
                    # Match "名字：张三" or "- 称呼：小王"
                    for prefix in ("名字：", "称呼：", "姓名："):
                        if prefix in stripped:
                            user_label = stripped.split(prefix, 1)[-1].strip()[:6]
                            break
    except Exception:
        pass

    return {
        "core": {
            "user": {"label": user_label, "color": "#ffd700"},
            "ai": {"label": ai_label, "color": "#a78bfa"},
        },
        "galaxies": galaxies,
        "connections": connections,
    }
