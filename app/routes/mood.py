"""Mood endpoints — calendar, timeline, affect, checkin, and AI insights."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import q, execute, init_db
from app.utils import get_llm, get_llm_model, extract_json

logger = logging.getLogger("psychology")

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# Pydantic models
# ═══════════════════════════════════════════════════════════════════════

class MoodCheckin(BaseModel):
    mood_emoji: str
    intensity: int = 5
    tags: list[str] = []
    note: str = ""


# ═══════════════════════════════════════════════════════════════════════
# Migrated from memory.py
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/mood/calendar")
def mood_calendar(days: int = 60, date_from: str = "", date_to: str = ""):
    """Return diary-entry dates with mood emoji for calendar rendering."""
    init_db()
    if date_from or date_to:
        where = []
        params = []
        if date_from:
            where.append("date >= %s")
            params.append(date_from)
        if date_to:
            where.append("date <= %s")
            params.append(date_to)
        clause = "WHERE " + " AND ".join(where)
        rows = q(
            f"SELECT date, chat_count, mood_emoji, content FROM diary_entries {clause} ORDER BY date DESC",
            params,
        )
    else:
        rows = q(
            "SELECT date, chat_count, mood_emoji, content FROM diary_entries ORDER BY date DESC LIMIT %s",
            [days],
        )
    result = []
    for r in rows:
        result.append({
            "date": str(r["date"]),
            "chat_count": r["chat_count"],
            "mood_emoji": r.get("mood_emoji") or "✨",
            "has_diary": bool(r.get("content")),
        })
    return result


@router.get("/api/mood/affect-history")
def mood_affect_history(days: int = 7):
    """Return daily Panksepp 6-dimension averages for the last N days."""
    init_db()
    rows = q(
        "SELECT date, seeking, play, care, fear, rage, panic "
        "FROM affect_history "
        "WHERE date >= CURRENT_DATE - INTERVAL '%s days' "
        "ORDER BY date ASC",
        [days],
    )
    if rows:
        return rows
    # Fallback: return today's current affect as single data point
    from services.emotion.affect import get_affect
    aff = get_affect()
    today = __import__("datetime").date.today().isoformat()
    return [{
        "date": today,
        "seeking": aff.get("seeking", 0.35),
        "play": aff.get("play", 0.25),
        "care": aff.get("care", 0.2),
        "fear": aff.get("fear", 0.1),
        "rage": aff.get("rage", 0.05),
        "panic": aff.get("panic", 0.1),
    }]


@router.get("/api/mood/timeline")
def mood_timeline(days: int = 7):
    """Return daily emotion distribution for the last N days."""
    init_db()
    rows = q(
        "SELECT DATE(created_at) AS date, emotion_label, COUNT(*) AS cnt "
        "FROM chat_history "
        "WHERE created_at >= NOW() - INTERVAL '%s days' "
        "GROUP BY DATE(created_at), emotion_label "
        "ORDER BY date DESC",
        [days],
    )
    # Build a per-date summary: {date: {label: count, total: N}}
    by_date = {}
    for r in (rows or []):
        d = str(r["date"])
        if d not in by_date:
            by_date[d] = {"total": 0, "labels": {}}
        by_date[d]["total"] += int(r["cnt"])
        by_date[d]["labels"][r["emotion_label"]] = int(r["cnt"])

    # Compute dominant emotion per day
    timeline = []
    for d in sorted(by_date.keys(), reverse=True):
        entry = by_date[d]
        labels = entry["labels"]
        dominant = max(labels, key=labels.get) if labels else ""
        timeline.append({
            "date": d,
            "total": entry["total"],
            "dominant": dominant,
            "labels": labels,
        })
    return timeline


# ═══════════════════════════════════════════════════════════════════════
# New: self-checkin
# ═══════════════════════════════════════════════════════════════════════

@router.post("/api/mood/checkin")
def mood_checkin(body: MoodCheckin):
    """Record a user self-reported mood checkin."""
    init_db()
    emoji = body.mood_emoji.strip()
    if not emoji:
        raise HTTPException(status_code=400, detail="mood_emoji is required")
    if len(emoji) > 10:
        raise HTTPException(status_code=400, detail="mood_emoji too long")
    intensity = max(1, min(10, body.intensity))
    tags = body.tags[:10] if body.tags else []
    note = (body.note or "")[:500]

    execute(
        "INSERT INTO mood_checkins (mood_emoji, intensity, tags, note) VALUES (%s, %s, %s, %s)",
        [emoji, intensity, tags, note],
    )
    return {"ok": True}


@router.get("/api/mood/checkins")
def mood_checkins(days: int = 30):
    """Return recent self-reported mood checkins."""
    init_db()
    rows = q(
        "SELECT id, mood_emoji, intensity, tags, note, created_at "
        "FROM mood_checkins "
        "WHERE created_at >= NOW() - INTERVAL '%s days' "
        "ORDER BY created_at DESC",
        [days],
    )
    for r in rows:
        r["date"] = str(r["created_at"])
    return rows


# ═══════════════════════════════════════════════════════════════════════
# New: AI weekly insight
# ═══════════════════════════════════════════════════════════════════════

_INSIGHT_PROMPT = """你是一位温柔的心理咨询师。根据用户过去一周的情绪数据，写一段50字以内的情绪洞察。

输出仅包含 JSON:
{
  "dominant_mood": "主导情绪（2-4字）",
  "trend": "趋势描述（如：逐渐好转 / 波动较大 / 持续低落 / 平稳愉悦）",
  "suggestion": "简短建议（10字以内）",
  "summary": "一段温暖的总结（40字以内）"
}

不要输出其他内容。"""


@router.get("/api/mood/insight")
def mood_insight(days: int = 7):
    """Generate a brief weekly mood insight using LLM."""
    init_db()

    # Gather data sources
    checkins = q(
        "SELECT mood_emoji, intensity, tags, created_at FROM mood_checkins "
        "WHERE created_at >= NOW() - INTERVAL '%s days' ORDER BY created_at ASC",
        [days],
    )
    affect_rows = q(
        "SELECT date, seeking, play, care, fear, rage, panic FROM affect_history "
        "WHERE date >= CURRENT_DATE - INTERVAL '%s days' ORDER BY date ASC",
        [days],
    )
    timeline_rows = q(
        "SELECT DATE(created_at) AS date, emotion_label, COUNT(*) AS cnt "
        "FROM chat_history "
        "WHERE created_at >= NOW() - INTERVAL '%s days' "
        "GROUP BY DATE(created_at), emotion_label ORDER BY date ASC",
        [days],
    )

    # Build a lightweight text summary for the LLM
    parts = []
    if checkins:
        emoji_summary = ", ".join(
            f"{c['mood_emoji']}(强度{c['intensity']})" for c in checkins[-14:]
        )
        parts.append(f"用户自检情绪: {emoji_summary}")
    if affect_rows:
        latest = affect_rows[-1]
        parts.append(
            f"Panksepp维度: 探索{latest['seeking']:.2f} 嬉戏{latest['play']:.2f} "
            f"关怀{latest['care']:.2f} 恐惧{latest['fear']:.2f} "
            f"愤怒{latest['rage']:.2f} 悲伤{latest['panic']:.2f}"
        )
    if timeline_rows:
        tl_summary = ", ".join(
            f"{r['date'].isoformat() if hasattr(r['date'], 'isoformat') else str(r['date'])}"
            f"({r['emotion_label']}×{r['cnt']})"
            for r in timeline_rows[-14:]
        )
        parts.append(f"聊天情绪: {tl_summary}")

    if not parts:
        return {
            "dominant_mood": "暂无数据",
            "trend": "等待记录",
            "suggestion": "记录你的第一条情绪吧",
            "summary": "开始记录情绪，我会陪你一起观察内心的变化。",
        }

    user_msg = "\n".join(parts)

    # Call LLM
    client = get_llm()
    if client is None:
        logger.warning("[mood/insight] No LLM configured, returning empty insight")
        return {
            "dominant_mood": "—",
            "trend": "—",
            "suggestion": "配置 LLM 以生成洞察",
            "summary": "需要先配置 AI 模型才能生成情绪洞察。",
        }

    try:
        model = get_llm_model()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _INSIGHT_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content or ""
        data = extract_json(raw)
        if data:
            return {
                "dominant_mood": str(data.get("dominant_mood", "—")),
                "trend": str(data.get("trend", "—")),
                "suggestion": str(data.get("suggestion", "—")),
                "summary": str(data.get("summary", "—")),
            }
        else:
            logger.warning("[mood/insight] Failed to parse LLM response: %s", raw[:200])
            return {
                "dominant_mood": "—",
                "trend": "—",
                "suggestion": "—",
                "summary": raw[:100] if raw else "分析暂不可用",
            }
    except Exception:
        logger.warning("[mood/insight] LLM call failed", exc_info=True)
        return {
            "dominant_mood": "—",
            "trend": "—",
            "suggestion": "稍后再试",
            "summary": "暂时无法生成情绪洞察，请稍后再试。",
        }
