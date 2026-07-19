"""User Model Synthesis — aggregates ~20 context sources into a unified portrait.

Reads raw data from affect, affinity, life domains, knowledge graph, personality,
crystals, conversation goals, attachment, drives, and contagion modules, then
synthesizes a concise 200-400 char Chinese portrait for system prompt injection.

No extra LLM cost — purely rule-based template synthesis with 60s cache.
"""

import json as _stdlib_json
import logging
import os
import time
from datetime import datetime, timezone

from app.config import MEMORY_DIR
from app.db import q

logger = logging.getLogger("emoji-chat")

_cache: tuple[str, float] | None = None
CACHE_TTL = 60  # seconds


def _get_raw_data() -> dict:
    """Gather raw structured data from all context sources."""
    data: dict = {}

    # ── Affect (Panksepp 6D, from DB) ──
    try:
        rows = q("SELECT dimension, value FROM affect_state")
        data["affect"] = {r["dimension"]: round(r["value"], 3) for r in rows}
    except Exception:
        data["affect"] = {}

    # ── Affinity (10D relationship, from DB) ──
    try:
        rows = q("SELECT dimension, value FROM affinity")
        data["affinity"] = {r["dimension"]: round(r["value"], 3) for r in rows}
    except Exception:
        data["affinity"] = {}

    # ── Life domains (from JSON file) ──
    try:
        from services.psych.life_domains import _load as load_domains
        data["life_domains"] = load_domains()
    except Exception:
        data["life_domains"] = {}

    # ── Personality (from JSON file) ──
    try:
        from services.identity.personality import load_personality
        data["personality"] = load_personality()
    except Exception:
        data["personality"] = {}

    # ── Knowledge Graph (from DB) ──
    try:
        from services.memory.knowledge_graph import get_current_state, get_temporal_insight
        data["kg_state"] = get_current_state()
        data["kg_temporal"] = get_temporal_insight()
    except Exception:
        data["kg_state"] = []
        data["kg_temporal"] = ""

    # ── Conversation goal (from JSON file) ──
    try:
        from services.psych.conversation_goal import _load_state as load_goal
        data["goal"] = load_goal()
    except Exception:
        data["goal"] = {}

    # ── Attachment style (from JSON file) ──
    try:
        from app.config import STYLE_PATH
        if os.path.exists(STYLE_PATH):
            with open(STYLE_PATH) as _f:
                data["attachment"] = _stdlib_json.load(_f)
    except Exception:
        data["attachment"] = {}

    # ── Drives (from DB) ──
    try:
        from services.drive.engine import get_drive_values
        data["drives"] = get_drive_values()
    except Exception:
        data["drives"] = {}

    # ── Emotional contagion (from JSON file) ──
    try:
        from services.emotion.contagion import _load_state as load_contagion
        data["contagion"] = load_contagion()
    except Exception:
        data["contagion"] = {}

    return data


def synthesize_portrait(data: dict) -> str:
    """Synthesize raw data into a concise Chinese user portrait (~200-400 chars)."""

    parts: list[str] = []

    # ── 1. Personality foundation ──
    personality = data.get("personality", {})
    ocean = personality.get("ocean", {})
    mbti = personality.get("mbti", "ENFP")
    archetype = personality.get("archetype", "explorer")

    archetype_cn = {
        "explorer": "探索者", "guardian": "守护者", "jester": "小丑",
        "confidant": "知己", "visionary": "理想家",
    }.get(archetype, "探索者")

    trait_cn = {
        "openness": "开放", "conscientiousness": "尽责",
        "extraversion": "外向", "agreeableness": "宜人", "neuroticism": "神经质",
    }
    high_traits = [cn for dim, cn in trait_cn.items() if ocean.get(dim, 0.5) > 0.65]
    low_traits = [cn for dim, cn in trait_cn.items() if ocean.get(dim, 0.5) < 0.35]

    personality_str = f"性格{archetype_cn}/{mbti}"
    if high_traits:
        personality_str += f"，偏{''.join(high_traits)}"
    parts.append(personality_str)

    # ── 2. Emotional state ──
    affect = data.get("affect", {})
    if affect:
        dominant_dim = max(affect, key=affect.get)  # type: ignore[arg-type]
        dominant_val = affect[dominant_dim]
        labels = {
            "seeking": "好奇探索中", "play": "心情愉悦", "care": "渴望亲密",
            "fear": "有些焦虑", "rage": "情绪激动", "panic": "情绪低落",
        }
        if dominant_val > 0.2:
            parts.append(f"当前{labels.get(dominant_dim, dominant_dim)}")

    # ── 3. Relationship status ──
    affinity = data.get("affinity", {})
    warmth = affinity.get("warmth", 0.5)
    trust = affinity.get("trust", 0.4)
    intimacy = affinity.get("intimacy", 0.2)

    if warmth > 0.55 or intimacy > 0.25:
        if intimacy > 0.5:
            rel_str = "关系非常亲密"
        elif warmth > 0.6:
            rel_str = "关系温暖默契"
        else:
            rel_str = "关系逐渐熟悉"
        if trust > 0.5:
            rel_str += "，信任度较高"
        parts.append(rel_str)

    # ── 4. Life domains ──
    domains = data.get("life_domains", {})
    if domains:
        active = [
            (k, v) for k, v in domains.items()
            if isinstance(v, dict) and v.get("salience", 0) > 0.05
        ]
        active.sort(key=lambda x: x[1].get("salience", 0), reverse=True)
        if active:
            domain_labels = {
                "work": "工作", "relationships": "人际关系", "health": "健康",
                "hobbies": "兴趣爱好", "finance": "财务", "growth": "个人成长",
            }
            top = [domain_labels.get(k, k) for k, _ in active[:2]]
            parts.append(f"最近关注{'和'.join(top)}")

    # ── 5. Key facts from KG (profile layer only) ──
    kg_state = data.get("kg_state", [])
    if kg_state:
        profile_types = {"food", "hobby", "work", "person", "tech"}
        key_facts = [s for s in kg_state if s.get("type") in profile_types][:3]
        if key_facts:
            relation_cn = {
                "likes": "喜欢", "loves": "热爱", "prefers": "偏好",
                "works_at": "在", "studies": "学",
            }
            fact_strs = []
            for s in key_facts:
                rel = relation_cn.get(s.get("relation", ""), s.get("relation", ""))
                fact_strs.append(f"{rel}{s.get('name', '')}")
            if fact_strs:
                parts.append("已知：" + "、".join(fact_strs))

    # ── 6. Conversation goal ──
    goal = data.get("goal", {})
    goal_type = goal.get("goal", goal.get("type", ""))  # compat with both keys
    if goal_type and goal_type != "small_talk":
        goal_labels = {
            "venting": "正在倾诉发泄", "advice_seeking": "在寻求建议",
            "sharing": "在分享日常", "debate": "在探讨问题",
        }
        goal_str = goal_labels.get(goal_type, "")
        turns = goal.get("turns_in_goal", goal.get("turns", 0))
        if goal_str and turns >= 2:
            parts.append(f"当前{goal_str}（持续{turns}轮）")

    # ── 7. Attachment style ──
    attachment = data.get("attachment", {})
    if attachment and attachment.get("style"):
        style_cn = {
            "secure": "安全型依恋", "anxious": "焦虑型依恋",
            "avoidant": "回避型依恋",
        }
        style_str = style_cn.get(attachment["style"], "")
        if style_str:
            parts.append(f"依恋风格偏{style_str}")

    # ── 8. Temporal insights from KG ──
    kg_temporal = data.get("kg_temporal", "")
    if kg_temporal:
        # Truncate temporal insight to single line for brevity
        first_line = kg_temporal.split("\n")[0]
        if len(first_line) < 100:
            parts.append(first_line)

    # ── Assemble ──
    if not parts:
        return ""

    portrait = "## 对你的了解（综合画像，仅供参考，不要逐条复述）\n"
    portrait += "用户" + "；".join(parts) + "。"

    # ── Guidance from contagion ──
    contagion = data.get("contagion", {})
    comfort_stats = contagion.get("comfort_stats", {})
    if comfort_stats and comfort_stats.get("uses", 0) >= 3:
        improved = comfort_stats.get("improved", 0)
        worsened = comfort_stats.get("worsened", 0)
        total = comfort_stats.get("uses", 1)
        if total > 0:
            rate = improved / total
            if rate >= 0.6:
                portrait += "\n（陪伴式倾听对你比较有效）"
            elif worsened / total >= 0.5:
                portrait += "\n（目前还在摸索怎么更好地陪伴你）"

    # Truncate to ~450 chars max
    if len(portrait) > 500:
        portrait = portrait[:497] + "..."

    return portrait


def get_user_portrait(force_refresh: bool = False) -> str:
    """Get the unified user portrait, cached for 60 seconds."""
    global _cache
    now = time.time()
    if not force_refresh and _cache and (now - _cache[1]) < CACHE_TTL:
        return _cache[0]

    try:
        data = _get_raw_data()
        portrait = synthesize_portrait(data)
        _cache = (portrait, now)
        return portrait
    except Exception:
        logger.warning("Failed to synthesize user portrait", exc_info=True)
        return _cache[0] if _cache else ""


# ── Proactive Care Context ────────────────────────────────────────────────────

def get_proactive_care_context() -> str:
    """Detect situations warranting proactive care and return context hints.

    Three scenarios:
    1. Return after long absence (>24h since last chat)
    2. Sustained low mood (high negative affect across recent turns)
    3. Important date approaching (from KG entities, within 7 days)
    """
    hints: list[str] = []

    # ── 1. Return after long absence ──
    try:
        from app.config import ARCHIVE_PATH
        if os.path.exists(ARCHIVE_PATH):
            with open(ARCHIVE_PATH) as f:
                lines = f.readlines()
            if lines:
                last_line = _stdlib_json.loads(lines[-1].strip())
                last_ts_str = last_line.get("timestamp", "")
                if last_ts_str:
                    last_ts = datetime.fromisoformat(last_ts_str)
                    gap_hours = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
                    if gap_hours > 24:
                        days = int(gap_hours / 24)
                        hints.append(
                            f"用户{days}天没来了，这是久别重逢。语气里可以带一点想念和欣喜，"
                            "但不要让对方有压力。可以自然地问一句'这几天还好吗'。"
                        )
    except Exception:
        pass

    # ── 2. Sustained low mood ──
    try:
        from services.emotion.affect import get_affect, _load_prev_state
        curr = get_affect()
        prev = _load_prev_state()
        if curr and prev:
            neg_dims = ["panic", "fear", "rage"]
            curr_neg = sum(curr.get(d, 0) for d in neg_dims)
            prev_neg = sum(prev.get(d, 0) for d in neg_dims)
            # Sustained high negative affect across turns
            if curr_neg > 0.6 and prev_neg > 0.5:
                hints.append(
                    "用户情绪已经低落了好一阵子。这轮可以更主动地关心一下，"
                    "问问他是不是遇到了什么事情。保持温柔陪伴的姿态。"
                )
            elif curr.get("panic", 0) > 0.4:
                hints.append(
                    "用户当前情绪低落。考虑主动表达关心和陪伴，但不要强迫对方说出来。"
                    "有时候一个'我在呢'比追问更有力。"
                )
    except Exception:
        pass

    # ── 3. Important dates ──
    try:
        from services.memory.knowledge_graph import get_current_state
        kg = get_current_state()
        # Look for date-related entities
        date_keywords = ["生日", "纪念日", "考试", "面试", "答辩", "入职", "毕业", "婚礼", "旅行"]
        for s in kg:
            name = s.get("name", "")
            if any(dk in name for dk in date_keywords):
                hints.append(f"用户曾提到'{name}'，如果时间接近可以在对话中自然提起。")
    except Exception:
        pass

    if not hints:
        return ""

    return "[主动关怀提示]\n" + "\n".join(f"- {h}" for h in hints[:2]) + "\n（自然表达，不要生硬）"


# ── Narrative Continuity ──────────────────────────────────────────────────────

_TIMELINE_PATH = os.path.join(MEMORY_DIR, "timeline.json")


def get_session_anchor() -> str:
    """Return context about the last conversation for cross-session continuity.

    Reads the last 1-2 conversation exchanges from the archive and produces
    a brief anchor so the AI can naturally reference past conversations.
    """
    try:
        from app.config import ARCHIVE_PATH
        if not os.path.exists(ARCHIVE_PATH):
            return ""

        with open(ARCHIVE_PATH) as f:
            lines = f.readlines()

        if len(lines) < 2:
            return ""

        # Read last 2 turns
        recent = lines[-4:] if len(lines) >= 4 else lines[-2:]
        last_user_msgs = []
        for line in recent[-4:]:
            try:
                entry = _stdlib_json.loads(line.strip())
                msg = entry.get("user", "")
                if msg and len(msg) > 5:
                    last_user_msgs.append(msg[:80])
            except Exception:
                pass

        if not last_user_msgs:
            return ""

        # Get the last meaningful topic
        last_topic = last_user_msgs[-1] if last_user_msgs else ""
        if len(last_topic) < 5:
            return ""

        last_ts_str = ""
        try:
            last_ts_str = _stdlib_json.loads(lines[-1].strip()).get("timestamp", "")
        except Exception:
            pass

        time_hint = ""
        if last_ts_str:
            try:
                last_ts = datetime.fromisoformat(last_ts_str)
                gap_min = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
                if gap_min > 60:
                    time_hint = f"（{int(gap_min/60)}小时前）"
                elif gap_min > 5:
                    time_hint = f"（{int(gap_min)}分钟前）"
            except Exception:
                pass

        anchor = f"[上次对话记忆锚点]\n上次聊到：\"{last_topic}\"{time_hint}\n"
        anchor += "可以自然地衔接上次的话题，但不要刻意复述原话。"
        return anchor
    except Exception:
        return ""


def get_timeline_context() -> str:
    """Return the relationship timeline for context injection.

    Tracks: first chat date, total chat days, total messages exchanged.
    Persisted to timeline.json.
    """
    try:
        from app.config import ARCHIVE_PATH
        if not os.path.exists(ARCHIVE_PATH):
            return ""

        # Load or compute timeline
        timeline = {}
        if os.path.exists(_TIMELINE_PATH):
            with open(_TIMELINE_PATH) as f:
                timeline = _stdlib_json.load(f)

        with open(ARCHIVE_PATH) as f:
            total_lines = sum(1 for _ in f)

        first_date = timeline.get("first_date", "")
        if not first_date and total_lines > 0:
            with open(ARCHIVE_PATH) as f:
                first_line = f.readline().strip()
                first_entry = _stdlib_json.loads(first_line)
                first_date = first_entry.get("timestamp", "")[:10]

        # Compute total days
        total_days = 0
        if first_date:
            try:
                first_dt = datetime.fromisoformat(first_date).date()
                total_days = (datetime.now(timezone.utc).date() - first_dt).days + 1
            except Exception:
                pass

        # Compute milestones
        milestone = ""
        if total_lines >= 500 and not timeline.get("m500_noted"):
            milestone = "\n（祝贺！你们已经交换了500条消息，这是一段值得珍惜的友谊）"
            timeline["m500_noted"] = True
        elif total_lines >= 100 and not timeline.get("m100_noted"):
            milestone = "\n（你们已经聊了100条消息了，关系正在逐渐加深）"
            timeline["m100_noted"] = True

        # Save updated timeline
        timeline["first_date"] = first_date
        timeline["total_lines"] = total_lines
        os.makedirs(os.path.dirname(_TIMELINE_PATH), exist_ok=True)
        with open(_TIMELINE_PATH, "w") as f:
            _stdlib_json.dump(timeline, f, ensure_ascii=False, indent=2)

        if total_lines < 20:
            return ""

        parts = []
        if total_days >= 7:
            parts.append(f"我们已经相识{total_days}天，交换了{total_lines}条消息")
        elif total_lines >= 50:
            parts.append(f"我们已交换了{total_lines}条消息，关系正在升温")

        if milestone:
            parts.append(milestone.strip())

        if parts:
            return "[我们的关系时间线]\n" + "。".join(parts) + "。\n（自然融入语气，不要刻意炫耀数据）" + milestone

        return ""
    except Exception:
        return ""

