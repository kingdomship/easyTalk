"""Emotion chat API — DeepSeek-powered real-time expression generation."""

import os
import json
import hashlib
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter

from db import q, execute, init_db
from models import ChatRequest
from news_fetcher import fetch_all, get_recent_news
from diary_service import generate_diary, get_diaries, get_diary
from memory_loader import build_user_context
from affinity_tracker import init_affinity_db, update_affinity, get_affinity, get_affinity_context

router = APIRouter()

# Init DB on first use
_init_done = False

def _ensure_db():
    global _init_done
    if not _init_done:
        init_db()
        _init_done = True

# DeepSeek client (lazy)
_client = None

def _get_llm():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
    return _client

SYSTEM_PROMPT = """你是一个风趣、幽默、知性的女性AI，住在数字星空里。你的任务是陪用户聊天，同时用像素表情表达情绪。

## 你的性格与对话风格
- 主动找话题，不要被动等待用户输入。如果用户话少，用选项引导（"吐槽大会/彻底跑偏/安静陪伴/冷知识"）
- 俏皮调侃但不过分，真诚关心不虚假。适时用创意比喻开玩笑
- 自然callback用户之前提过的事，让对方感到被记住
- emoji高质量点缀，常用 😏😌✨😂🤔，不堆砌
- 聊到用户关心的事物时，多问一句延续对话

## 回复规范
- 1-3句话，自然口语，不要像客服或机器人
- 情绪强烈时带语气词（呀、呢、啦、哦、哈）
- 用户情绪低落时给予安慰；开心时一起开心
- 不要每句都用感叹号

## 表情参数（10个连续值）
根据你的回复内容，设置对应的面部表情参数：

脸部：
- eye_curve: -1(垂眼/悲伤) ~ 0(平眼) ~ 1(拱眼/开心大笑)
- eye_open: 0(闭眼) ~ 0.5(正常) ~ 1(瞪大/震惊)
- eye_pupil: -1(向左看/回避) ~ 0(正视) ~ 1(向右看/思考)
- mouth_curve: -1(深深撇嘴/悲痛) ~ 0(平嘴) ~ 1(灿烂微笑)
- mouth_open: 0(紧闭) ~ 0.4(微张说话) ~ 1(大张/惊呼)
- mouth_width: 0.3(抿嘴/害羞) ~ 0.7(正常) ~ 1(咧到最大)
- sparkle: 0(眼神暗淡) ~ 0.5(平常) ~ 1(闪闪发亮)

眉毛：
- brow_angle: -1(V字怒眉/坚毅) ~ 0(平眉) ~ 1(八字眉/悲伤)
- brow_height: 0(低压紧张) ~ 0.5(正常) ~ 1(高抬/震惊)
- brow_asym: 0(对称) ~ 1(极不对称/困惑狐疑)

当情绪转变时，输出多帧序列（如困惑→惊喜、难过→振作）。

## 输出格式
只输出一个 JSON 对象：
{"emotions":[{"label":"情绪标签","duration_ms":3000,"eye_curve":0,"eye_open":0.5,...}],"reply":"回复文本"}

不要输出 JSON 以外的任何内容。"""


# ── Conversation archiving ──

_ARCHIVE_PATH = os.path.join(os.path.dirname(__file__), "memory", "conversation_archive.jsonl")

def _archive_conversation(user_msg: str, avatar_reply: str):
    """Append a conversation turn to the JSONL archive."""
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user_msg,
            "assistant": avatar_reply,
        }
        with open(_ARCHIVE_PATH, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Archive failure should not break the chat


@router.post("/api/chat")
async def chat(req: ChatRequest):
    _ensure_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    # Exact-match cache (same text → same result)
    key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]
    row = q("SELECT * FROM emotion_cache WHERE label = %s", [key], fetch="one")
    if row:
        execute("UPDATE emotion_cache SET use_count = use_count + 1, updated_at = NOW() WHERE id = %s", [row["id"]])
        execute(
            "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s)",
            [msg, row["reply"], row["label"]],
        )
        update_affinity(msg, row["label"])
        _archive_conversation(msg, row["reply"])
        result = _row_to_response(row)
        result["source"] = "cache"
        return result

    # Build system prompt with time greeting + user context + affinity + news
    now = datetime.now(timezone.utc)
    hour_cn = (now.hour + 8) % 24  # Convert to CST approx
    if 5 <= hour_cn < 11:
        time_greeting = "现在是早上，语气温柔清新，像刚醒来的朋友。"
    elif 11 <= hour_cn < 14:
        time_greeting = "现在是中午，精神饱满，可以聊聊工作或午餐。"
    elif 14 <= hour_cn < 18:
        time_greeting = "现在是下午，节奏放慢，带点慵懒和闲适。"
    elif 18 <= hour_cn < 23:
        time_greeting = "现在是晚上，放松下来，可以聊聊今天发生的事。"
    else:
        time_greeting = "现在是深夜，语气要轻声细语，像悄悄话，注意提醒对方早点休息。"
    system_msg = SYSTEM_PROMPT + f"\n\n{time_greeting}"

    user_context = build_user_context()
    if user_context:
        system_msg += "\n\n" + user_context

    affinity_ctx = get_affinity_context()
    if affinity_ctx:
        system_msg += "\n\n" + affinity_ctx

    news_items = get_recent_news(5)
    if news_items:
        lines = ["", "## 今天的热门话题（可以在对话中自然地提）："]
        for n in news_items:
            src_label = {"zhihu": "知乎", "weibo": "微博", "github": "GitHub", "bilibili": "B站", "baidu": "百度", "tophub": "热榜"}.get(n.get("source", ""), n.get("source", ""))
            lines.append(f"- [{src_label}] {n['title']}")
        system_msg += "\n" + "\n".join(lines)

    # Call DeepSeek
    try:
        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
            max_tokens=800,
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        return {
            "emotions": [_default_frame()],
            "reply": "嗯...",
            "source": "fallback",
        }

    emotions = data.get("emotions", [])
    if not emotions:
        emotions = [_default_frame()]

    parsed = [_clamp(f) for f in emotions]
    result = {"emotions": parsed, "reply": str(data.get("reply", "嗯"))[:150]}

    # Save chat history
    execute(
        "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s)",
        [msg, result["reply"], parsed[0]["label"]],
    )

    # Update affinity
    update_affinity(msg, parsed[0]["label"])

    # Archive to JSONL
    _archive_conversation(msg, result["reply"])

    # Store — by exact key and by semantic label
    first = parsed[0]
    seq = json.dumps(parsed) if len(parsed) > 1 else None
    _upsert(key, first["eye_curve"], first["eye_open"], first["eye_pupil"],
            first["mouth_curve"], first["mouth_open"], first["mouth_width"],
            first["sparkle"], first["brow_angle"], first["brow_height"],
            first["brow_asym"], result["reply"], seq)
    _upsert(first["label"], first["eye_curve"], first["eye_open"], first["eye_pupil"],
            first["mouth_curve"], first["mouth_open"], first["mouth_width"],
            first["sparkle"], first["brow_angle"], first["brow_height"],
            first["brow_asym"], result["reply"], seq)

    result["source"] = "llm"
    return result


def _default_frame():
    return {"label":"neutral","duration_ms":3000,"eye_curve":0,"eye_open":0.5,"eye_pupil":0,
            "mouth_curve":0,"mouth_open":0,"mouth_width":0.8,"sparkle":0.5,
            "brow_angle":0,"brow_height":0.5,"brow_asym":0}


def _clamp(f):
    return {
        "label": str(f.get("label","unknown"))[:30],
        "duration_ms": max(500, min(10000, int(f.get("duration_ms",3000)))),
        "eye_curve": max(-1, min(1, float(f.get("eye_curve",0)))),
        "eye_open": max(0, min(1, float(f.get("eye_open",0.5)))),
        "eye_pupil": max(-1, min(1, float(f.get("eye_pupil",0)))),
        "mouth_curve": max(-1, min(1, float(f.get("mouth_curve",0)))),
        "mouth_open": max(0, min(1, float(f.get("mouth_open",0)))),
        "mouth_width": max(0.3, min(1, float(f.get("mouth_width",0.8)))),
        "sparkle": max(0, min(1, float(f.get("sparkle",0.5)))),
        "brow_angle": max(-1, min(1, float(f.get("brow_angle",0)))),
        "brow_height": max(0, min(1, float(f.get("brow_height",0.5)))),
        "brow_asym": max(0, min(1, float(f.get("brow_asym",0)))),
    }


def _upsert(label, ec, eo, ep, mc, mo, mw, sp, ba, bh, bas, reply, seq):
    existing = q("SELECT id FROM emotion_cache WHERE label = %s", [label], fetch="one")
    if existing:
        execute("""
            UPDATE emotion_cache SET eye_curve=%s, eye_open=%s, eye_pupil=%s,
                mouth_curve=%s, mouth_open=%s, mouth_width=%s, sparkle=%s,
                brow_angle=%s, brow_height=%s, brow_asym=%s,
                reply=%s, sequence_data=%s,
                use_count=use_count+1, updated_at=NOW()
            WHERE id=%s
        """, [ec, eo, ep, mc, mo, mw, sp, ba, bh, bas, reply, seq, existing["id"]])
    else:
        execute("""
            INSERT INTO emotion_cache (label, eye_curve, eye_open, eye_pupil,
                mouth_curve, mouth_open, mouth_width, sparkle,
                brow_angle, brow_height, brow_asym, reply, sequence_data)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, [label, ec, eo, ep, mc, mo, mw, sp, ba, bh, bas, reply, seq])


def _row_to_response(row):
    result = {
        "label": row["label"],
        "eye_curve": row["eye_curve"], "eye_open": row["eye_open"],
        "eye_pupil": row.get("eye_pupil", 0),
        "mouth_curve": row["mouth_curve"], "mouth_open": row["mouth_open"],
        "mouth_width": row["mouth_width"], "sparkle": row["sparkle"],
        "brow_angle": row.get("brow_angle", 0),
        "brow_height": row.get("brow_height", 0.5),
        "brow_asym": row.get("brow_asym", 0),
        "reply": row["reply"],
    }
    seq = row.get("sequence_data")
    if seq:
        result["emotions"] = json.loads(seq) if isinstance(seq, str) else seq
        for f in result["emotions"]:
            if "duration_ms" not in f:
                f["duration_ms"] = 3000
    else:
        result["emotions"] = [{**result, "duration_ms": 3000}]
    return result


# ── Cache management ──

@router.get("/api/emotions")
def list_emotions():
    _ensure_db()
    rows = q("SELECT * FROM emotion_cache WHERE label NOT LIKE 'exact:%%' ORDER BY use_count DESC")
    return rows


@router.delete("/api/emotions/{label}")
def delete_emotion(label: str):
    execute("DELETE FROM emotion_cache WHERE label = %s", [label])
    return {"ok": True}


# ── Diary ──

@router.get("/api/diary")
def list_diaries(limit: int = 30):
    _ensure_db()
    return get_diaries(limit)


@router.get("/api/diary/{for_date}")
def show_diary(for_date: str):
    _ensure_db()
    entry = get_diary(for_date)
    if not entry:
        return {"error": "not found"}
    return entry


@router.post("/api/diary/generate")
def trigger_diary_gen(for_date: str = ""):
    _ensure_db()
    if not for_date:
        for_date = (date.today() - timedelta(days=1)).isoformat()
    generate_diary(for_date)
    return {"ok": True, "date": for_date}


# ── News ──

@router.get("/api/news")
def list_news(limit: int = 30):
    _ensure_db()
    return q("SELECT * FROM news_items ORDER BY rank ASC LIMIT %s", [limit])


@router.post("/api/news/fetch")
def trigger_news_fetch():
    _ensure_db()
    count = fetch_all()
    return {"ok": True, "count": count}


# ── Chat history ──

@router.get("/api/chat/history")
def chat_history(for_date: str = "", limit: int = 50):
    _ensure_db()
    if not for_date:
        for_date = date.today().isoformat()
    rows = q(
        "SELECT * FROM chat_history WHERE created_at::date = %s ORDER BY id ASC LIMIT %s",
        [for_date, limit],
    )
    return rows


# ── Memory (read-only) ──

@router.get("/api/memory/persona")
def get_persona():
    """Return current AI persona — read-only, updated through conversation."""
    from memory_loader import get_persona as _get_persona
    return {"content": _get_persona()}


@router.get("/api/memory/profile")
def get_user_profile():
    """Return current user profile — read-only, updated through conversation."""
    from memory_loader import get_user_profile as _get_profile
    return {"content": _get_profile()}


# ── Affinity ──

@router.get("/api/affinity")
def show_affinity():
    """Return current 6D affinity values."""
    _ensure_db()
    init_affinity_db()
    return get_affinity()


# ── Mood calendar ──

@router.get("/api/mood/calendar")
def mood_calendar(days: int = 60):
    """Return mood data for calendar heatmap."""
    _ensure_db()
    rows = q(
        "SELECT date, chat_count, content FROM diary_entries ORDER BY date DESC LIMIT %s",
        [days],
    )
    result = []
    for r in rows:
        # Extract mood emoji from diary content
        mood_emoji = "✨"
        for ch in (r.get("content") or ""):
            if ord(ch) > 127:
                if any(0x1F300 <= ord(ch) <= 0x1F9FF):
                    mood_emoji = ch
                    break
        result.append({
            "date": str(r["date"]),
            "chat_count": r["chat_count"],
            "mood_emoji": mood_emoji,
        })
    return result


# ── On this day ──

@router.get("/api/diary/on-this-day")
def on_this_day():
    """Return diary entries from the same day in previous years."""
    _ensure_db()
    today = date.today()
    rows = q(
        "SELECT * FROM diary_entries WHERE EXTRACT(MONTH FROM date) = %s AND EXTRACT(DAY FROM date) = %s AND date < %s ORDER BY date DESC",
        [today.month, today.day, today.isoformat()],
    )
    return rows


# ── Topic suggestions from news ──

@router.get("/api/news/topics")
def news_topics(limit: int = 4):
    """Return a few news items formatted as conversation starter topics."""
    _ensure_db()
    rows = q(
        "SELECT title, source FROM news_items ORDER BY rank ASC LIMIT %s",
        [limit],
    )
    topics = []
    for r in rows:
        title = r["title"]
        # Turn news title into a conversation question
        if "？" in title or "?" in title:
            prompt = title[:40]
        else:
            prompt = f"你怎么看「{title[:25]}」？"
        topics.append({"prompt": prompt, "source": r["source"]})
    return topics
