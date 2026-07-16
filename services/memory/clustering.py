"""Memory constellation builder — clusters memories into topic galaxies.

Provides data for the frontend Canvas star map visualization.
Each "galaxy" is a topic cluster; "stars" are individual crystal memories
with position, size, and importance derived from multiple signal dimensions.

Importance is computed from four weighted dimensions:
  1. Crystal persistence — LLM-distilled memories with Ebbinghaus decay
  2. Milestone events — relationship threshold crossings (intrinsically significant)
  3. Usage frequency — log-scaled use_count (smooth, avoids saturation at 20)
  4. Narrative cross-reference — bonus when content appears in episodes
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
    """Compute a star's position within its galaxy's elliptical orbit."""
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


def _log_importance(use_count: int) -> float:
    """Log-scaled importance from usage frequency.

    use_count=1 -> 0.15, 3 -> 0.4, 5 -> 0.55, 10 -> 0.72, 20 -> 0.9, 50+ -> 1.0

    Logarithmic scaling avoids the linear formula's problem where
    a trivial greeting repeated 20x outranks a one-time milestone event.
    """
    if use_count <= 0:
        return 0.1
    return round(min(1.0, math.log2(use_count + 1) / math.log2(21)), 3)


def _load_episode_terms() -> set[str]:
    """Extract meaningful Chinese bigrams from episode narratives.

    Used for cross-reference boosting: if a star's content overlaps
    with narrative episodes, it gains a bonus.
    """
    terms = set()
    try:
        from app.config import EPISODES_PATH
        if os.path.exists(EPISODES_PATH):
            with open(EPISODES_PATH) as f:
                for line in f:
                    try:
                        ep = json.loads(line)
                        text = ep.get("narrative", "")
                        for i in range(len(text) - 1):
                            chunk = text[i:i + 2]
                            if all('一' <= c <= '鿿' for c in chunk):
                                terms.add(chunk)
                    except Exception:
                        pass
    except Exception:
        pass
    return terms


# Keywords that signal a significant event / declaration / decision
_SIGNIFICANCE_MARKERS = [
    "宣布", "决定", "就是你了", "就是她了", "就是它了", "以后我就是",
    "正式", "从今天起", "从今往后", "记住", "别忘了", "这很重要",
    "我一直都在", "永远", "承诺", "约定", "答应我", "第一次",
    "终于", "最后决定", "定下来了", "锁定", "就是", "确认",
]


def _content_signal_boost(content: str) -> float:
    """Boost importance for content containing significance markers.

    Declarations, decisions, and emotional milestones deserve higher
    weight regardless of use_count.
    """
    boost = 0.0
    for marker in _SIGNIFICANCE_MARKERS:
        if marker in content:
            boost += 0.08
    return min(0.35, boost)


def _load_salience_multiplier() -> float:
    """Compute a salience-based multiplier for importance boosting.

    High surprise + reward moments → memories are more significant.
    Returns a multiplier in range [0.85, 1.3].
    """
    try:
        from services.emotion.salience import get_salience
        s = get_salience()
        if s:
            surprise = s.get("surprise", 0.1)
            reward = s.get("reward", 0.1)
            # Map to a gentle multiplier range
            return round(0.85 + surprise * 0.25 + reward * 0.2, 2)
    except Exception:
        pass
    return 1.0


def _extract_tag(content: str, source: str = "emotion", members: list | None = None) -> str:
    """Extract a meaningful topic tag from memory content.

    Uses heuristics to produce short, human-readable labels like
    "确定姓名" or "陆薇" instead of bare content prefixes.
    """
    # Crystal sources use their original tag (already a good label)
    if source == "crystal":
        # Crystal content format: "tag：crystal_description"
        if "：" in content:
            tag_part = content.split("：", 1)[0].strip()
            if 2 <= len(tag_part) <= 10:
                return tag_part

    # Milestone sources use the milestone name
    if source == "milestone":
        if "：" in content:
            tag_part = content.split("：", 1)[0].strip()
            if 2 <= len(tag_part) <= 10:
                return tag_part

    # Merged groups: find the dominant theme from member contents
    if members and len(members) > 1:
        return _extract_group_tag(members)

    # Try to extract a quoted name or highlighted term
    import re
    # 「...」or「...」
    bracket_match = re.search(r'[「「]([^」」]{2,10})[」」]', content)
    if bracket_match:
        return bracket_match.group(1)[:10]

    # **...** bold text
    bold_match = re.search(r'\*\*([^*]{2,10})\*\*', content)
    if bold_match:
        return bold_match.group(1)[:10]

    # Key action patterns: verb + object
    action_patterns = [
        (r'(选定|确定|决定|选择|命名|取名|起名|改名)[了]?[的]?[^\s，。,.,！,！]{0,4}'),
        (r'(第一次|首次|初次)[^\s，。,.,！,！]{0,6}'),
        (r'(宣布|宣告)[^\s，。,.,！,！]{0,6}'),
        (r'正式[^\s，。,.,！,！]{0,6}'),
    ]

    for pattern in action_patterns:
        match = re.search(pattern, content)
        if match:
            # Clean up dashes, asterisks, and other noise characters
            matched = re.sub(r'[——\*_""]', '', match.group(0))[:10]
            if matched:
                return matched

    # Entity extraction: look for 2-4 char proper name patterns near key terms
    # e.g., "叫 **石玉**" → "石玉"
    name_match = re.search(r'叫\s*[\*]*([^\s，,。,.*]{2,4})', content)
    if name_match:
        return re.sub(r'[——\*_]', '', name_match.group(1))[:10]

    # Fallback: extract the most meaningful short phrase
    # Remove punctuation, take a clean 8-char slice
    clean = re.sub(r'[^一-鿿\w]', '', content)
    if len(clean) >= 6:
        return clean[:8]

    return clean[:8] if clean else content[:8]


def _extract_group_tag(members: list) -> str:
    """Find the most representative tag for a merged group.

    Checks if any member is a crystal (has a clean tag), then falls back
    to finding the most common keyword among the group.
    """
    # Prefer crystal-sourced members for tag (they have clean labels)
    crystal_members = [m for m in members if m.get("source") == "crystal"]
    if crystal_members:
        best = max(crystal_members, key=lambda m: m.get("importance", 0))
        if "：" in best["content"]:
            return best["content"].split("：", 1)[0].strip()[:10]

    # Find the most frequent meaningful bigram across all members
    from collections import Counter
    bigram_counts = Counter()
    for m in members:
        c = m.get("content", "")
        seen = set()
        for i in range(len(c) - 1):
            chunk = c[i:i + 2]
            if all('一' <= ch <= '鿿' for ch in chunk):
                if chunk not in seen:
                    bigram_counts[chunk] += 1
                    seen.add(chunk)

    # Pick top bigrams and compose a tag
    top_bigrams = [b for b, _ in bigram_counts.most_common(3)]
    if top_bigrams:
        combined = "".join(top_bigrams)[:10]
        return combined

    return "记忆集群"


def _extract_summary(content: str, source: str = "emotion", members: list | None = None) -> str:
    """Extract a descriptive summary of variable length based on the event type.

    Different sources produce different kinds of summaries:
      - crystal/milestone: use the concise description already present
      - merged group: show a composite from the most important members
      - emotion_cache: use the content, cut at a natural sentence boundary
    """
    import re

    # Crystal: "tag：description" → return the description part
    if source == "crystal" and "：" in content:
        desc = content.split("：", 1)[1].strip()
        return desc[:120]

    # Milestone: "name：description" → return the description
    if source == "milestone" and "：" in content:
        desc = content.split("：", 1)[1].strip()
        return desc[:120]

    # Merged group: compose from member highlights
    if members and len(members) > 1:
        return _compose_group_summary(members)

    # Emotion cache / fallback: find a natural sentence break
    return _natural_truncation(content, target_len=100)


def _compose_group_summary(members: list) -> str:
    """Compose a summary for a merged memory cluster.

    Shows the most significant member's essence, plus a count of
    related memories.
    """
    # Prefer the crystal member for summary if available
    crystal_members = [m for m in members if m.get("source") == "crystal"]
    if crystal_members:
        best = max(crystal_members, key=lambda m: m.get("importance", 0))
        content = best.get("content", "")
        if "：" in content:
            desc = content.split("：", 1)[1].strip()
            return f"{desc}（含 {len(members)} 段相关记忆）"[:150]

    # Otherwise, pick the most important member
    best = max(members, key=lambda m: m.get("importance", 0))
    content = best.get("content", "")
    summary = _natural_truncation(content, target_len=80)
    if len(summary) < len(content):
        summary += f"（共 {len(members)} 段）"
    return summary[:150]


def _natural_truncation(text: str, target_len: int = 100) -> str:
    """Truncate text at a natural sentence boundary.

    Finds the nearest 。！？! ? or newline near target_len,
    rather than cutting mid-sentence.
    """
    if len(text) <= target_len:
        return text

    # Look for a sentence break within ±30% of target
    window = text[: int(target_len * 1.3)]
    break_chars = "。！？!?\n"

    # Find the last break character in the window
    best_pos = target_len
    for i in range(len(window) - 1, target_len // 2, -1):
        if window[i] in break_chars:
            best_pos = i + 1  # include the break char
            break

    return text[:best_pos]


def _merge_by_topic(memories: list) -> list:
    """Merge memories that share significant keyword overlap into topic clusters."""
    if len(memories) <= 1:
        return memories

    def _key_terms(text):
        terms = set()
        for i in range(len(text) - 1):
            chunk = text[i:i + 2]
            if all('一' <= c <= '鿿' or c.isalpha() for c in chunk):
                terms.add(chunk)
        return terms

    term_sets = [_key_terms(m["content"]) for m in memories]

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
            overlap = len(si & sj)
            if overlap >= 3 or (overlap >= 2 and overlap / min(len(si), len(sj)) > 0.3):
                union(i, j)

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
            best = max(group, key=lambda m: len(m["content"]))
            combined_importance = min(1.0, sum(m["importance"] for m in group))
            merged.append({
                "id": next_id,
                "content": best["content"][:100],
                "importance": combined_importance,
                "use_count": sum(m["use_count"] for m in group),
                "source": "merged",
                "_members": group,
            })
            next_id += 1

    return merged


def build_constellation() -> dict:
    """Build the full constellation data structure for frontend rendering.

    Importance now blends four weighted signals:
      - Crystal persistence (weight 0.35): LLM-distilled, salience-weighted,
        Ebbinghaus-decayed memories from crystals.jsonl
      - Milestone events (weight 0.30): Relationship threshold crossings
      - Usage frequency (weight 0.20): Log-scaled use_count from emotion_cache
      - Narrative boost (weight 0.15): Cross-reference bonus when content
        appears in distilled episodes

    Returns:
        {core: {user: {label, color}, ai: {label, color}},
         galaxies: [{topic, label, color, angle, stars: [...]}],
         connections: [{from_id, to_id}]}
    """
    episode_terms = _load_episode_terms()
    salience_mult = _load_salience_multiplier()

    all_memories = []
    seen_hashes = set()
    next_artificial_id = 100000

    def _add_memory(mem_id, content, importance, use_count, source="emotion"):
        key = hash(content[:80])
        if key in seen_hashes:
            return
        seen_hashes.add(key)
        all_memories.append({
            "id": mem_id,
            "content": content,
            "importance": float(importance),
            "use_count": int(use_count),
            "source": source,
        })

    # ── Source 1: Crystals (highest weight, LLM-distilled persistent memories) ──
    try:
        from services.memory.crystallization import get_crystals
        crystals = get_crystals(min_importance=0.0)
        for c in crystals:
            content = f"{c.get('tag', '')}：{c.get('crystal', '')}"[:100]
            if not content.strip():
                continue
            # Crystal importance is already salience-weighted + Ebbinghaus-decayed
            crystal_imp = c.get("current_importance", c.get("importance", 0.3))
            _add_memory(next_artificial_id, content,
                        round(crystal_imp, 3),
                        c.get("reinforcement_count", 1),
                        source="crystal")
            next_artificial_id += 1
    except Exception:
        logger.warning("Failed to load crystals for constellation", exc_info=True)

    # ── Source 2: Milestones (intrinsically significant events) ──
    try:
        from services.emotion.affinity import get_milestones
        milestones = get_milestones()
        for i, m in enumerate(milestones):
            name = m.get("name", "")
            desc = m.get("description", "")
            content = f"{name}：{desc}"[:100]
            # Milestones are inherently important — scale by milestone index
            # (later milestones = deeper relationship = higher importance)
            milestone_imp = 0.6 + i * 0.05  # 0.60, 0.65, 0.70, 0.75, 0.80
            _add_memory(next_artificial_id, content,
                        min(0.9, milestone_imp),
                        max(1, int(m.get("value", 0.5) * 10)),
                        source="milestone")
            next_artificial_id += 1
    except Exception:
        logger.warning("Failed to load milestones for constellation", exc_info=True)

    # ── Source 3: Emotion cache (log-scaled frequency + cross-reference) ──
    rows = q(
        "SELECT id, reply AS content, use_count, created_at "
        "FROM emotion_cache WHERE sequence_data IS NOT NULL OR use_count > 2 "
        "ORDER BY use_count DESC LIMIT 50"
    )
    for r in rows:
        content = (r.get("content") or r.get("reply") or "")[:100]
        if not content:
            continue

        use_count = int(r.get("use_count", 1))
        # Base: log-scaled frequency
        imp = _log_importance(use_count)

        # Content signal boost: declarations / decisions / milestones
        imp += _content_signal_boost(content)

        # Cross-reference boost: check if content overlaps with episode narratives
        content_terms = set()
        for i in range(len(content) - 1):
            chunk = content[i:i + 2]
            if all('一' <= c <= '鿿' for c in chunk):
                content_terms.add(chunk)
        if content_terms and episode_terms:
            overlap = content_terms & episode_terms
            if overlap:
                # More overlapping bigrams → stronger narrative connection
                narrative_bonus = min(0.25, len(overlap) * 0.05)
                imp += narrative_bonus

        # Apply salience multiplier
        imp *= salience_mult
        imp = min(1.0, imp)

        _add_memory(r["id"], content, round(imp, 3), use_count, source="emotion")

    # ── Source 4: System2 insights ──
    crystal_rows = q(
        "SELECT id, insight AS content, 1 AS use_count, created_at "
        "FROM system2_insights WHERE category = 'general' LIMIT 20"
    )
    for r in crystal_rows:
        content = (r.get("content") or "")[:100]
        if content:
            # Base 0.35 + salience boost, as these are deep analysis results
            imp = round(min(0.7, 0.35 + (salience_mult - 1.0) * 0.5), 3)
            _add_memory(r["id"] + 10000, content, imp,
                        r.get("use_count", 1), source="insight")

    # ── Fallback: if nothing loaded, use plain emotion_cache ──
    if not all_memories:
        fallback = q(
            "SELECT id, reply, use_count FROM emotion_cache "
            "WHERE reply != '' ORDER BY use_count DESC LIMIT 30"
        )
        for r in fallback:
            content = r["reply"][:80]
            if content:
                _add_memory(r["id"], content,
                            _log_importance(int(r.get("use_count", 1))),
                            r.get("use_count", 1), source="fallback")

    # ── Topic aggregation ──
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
            tag = _extract_tag(
                mem["content"],
                source=mem.get("source", "emotion"),
                members=mem.get("_members"),
            )
            stars.append({
                "id": mem["id"],
                "tag": tag,
                "summary": _extract_summary(
                    mem["content"],
                    source=mem.get("source", "emotion"),
                    members=mem.get("_members"),
                ),
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

    # ── Connections (lowered threshold from 0.4 → 0.25 for richer graph) ──
    connections = []
    for galaxy in galaxies:
        important_stars = [s for s in galaxy["stars"] if s["importance"] > 0.25]
        for i in range(len(important_stars)):
            for j in range(i + 1, min(i + 3, len(important_stars))):
                connections.append({
                    "from_id": important_stars[i]["id"],
                    "to_id": important_stars[j]["id"],
                })

    # ── Core labels from persona/profile ──
    user_label = "我"
    ai_label = "AI"
    try:
        from app.config import PERSONA_PATH, PROFILE_PATH
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
                    if "名字" in stripped and ("：" in stripped or ":" in stripped):
                        for sep in ("：", ":"):
                            parts = stripped.split(sep, 1)
                            if "名字" in parts[0] and len(parts) > 1:
                                ai_label = parts[1].strip()[:8]
                                break
                        if ai_label != "AI":
                            break
                    if ai_label == "AI" and "我是" in stripped:
                        rest = stripped.split("我是", 1)[1]
                        for sep in ("，", ",", "。", ".", "、", " "):
                            rest = rest.split(sep, 1)[0]
                        ai_label = rest.strip()[:8]
                        break
                    if "身份" in stripped:
                        role = stripped.split("：", 1)[-1].split("、")
                        ai_label = "".join(role[:2])[:8]
                        break
                    if stripped.startswith("#") and fallback_label is None:
                        fallback_label = stripped.lstrip("#").strip()[:8]
                else:
                    if fallback_label:
                        ai_label = fallback_label
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
