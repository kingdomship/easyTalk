"""Chat endpoints + helpers."""

import asyncio
import logging
import os
import json
import hashlib
import random
import threading
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.db import q, execute, init_db
from app.models import ChatRequest
from services.news import get_recent_news
from services.memory_loader import build_user_context
from services.memory_search import index_turn, build_memory_context
from services.affinity import update_affinity, get_affinity_context, adjust_expression_amplitude, scale_emotion_params
from services.prompt import SYSTEM_PROMPT, build_time_context

router = APIRouter()
logger = logging.getLogger("emoji-chat")

_CONDENSE_EVERY = 50
_condense_lock = threading.Lock()
_last_condense_count = 0

_init_done = False

def _ensure_db():
    global _init_done
    if not _init_done:
        init_db()
        _init_done = True

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

# Paths go up 3 levels: app/routes/chat.py → app/ → /app/
_BASE = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_ARCHIVE_PATH = os.path.join(_BASE, "memory", "conversation_archive.jsonl")


def _jitter(value: float, amount: float = 0.03) -> float:
    return value + (random.random() * 2 - 1) * amount


def _jitter_frame(frame: dict) -> dict:
    f = dict(frame)
    f["eye_curve"] = max(-1, min(1, _jitter(f.get("eye_curve", 0))))
    f["eye_open"] = max(0, min(1, _jitter(f.get("eye_open", 0.5), 0.02)))
    f["eye_pupil"] = max(-1, min(1, _jitter(f.get("eye_pupil", 0), 0.02)))
    f["mouth_curve"] = max(-1, min(1, _jitter(f.get("mouth_curve", 0))))
    f["mouth_open"] = max(0, min(1, _jitter(f.get("mouth_open", 0), 0.02)))
    f["mouth_width"] = max(0.3, min(1, _jitter(f.get("mouth_width", 0.8), 0.015)))
    f["sparkle"] = max(0, min(1, _jitter(f.get("sparkle", 0.5), 0.02)))
    f["brow_angle"] = max(-1, min(1, _jitter(f.get("brow_angle", 0))))
    f["brow_height"] = max(0, min(1, _jitter(f.get("brow_height", 0.5), 0.02)))
    f["brow_asym"] = max(0, min(1, _jitter(f.get("brow_asym", 0), 0.015)))
    return f


def _archive_conversation(user_msg: str, avatar_reply: str):
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user_msg,
            "assistant": avatar_reply,
        }
        with open(_ARCHIVE_PATH, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _maybe_condense():
    global _last_condense_count
    if not _condense_lock.acquire(blocking=False):
        return
    try:
        if not os.path.exists(_ARCHIVE_PATH):
            return
        with open(_ARCHIVE_PATH) as f:
            line_count = sum(1 for _ in f)
        if line_count - _last_condense_count < _CONDENSE_EVERY:
            return
        _last_condense_count = line_count

        with open(_ARCHIVE_PATH) as f:
            transcript_parts = []
            for line in f:
                try:
                    rec = json.loads(line)
                    user = rec.get("user", "")
                    assistant = rec.get("assistant", "")
                    if user:
                        transcript_parts.append(f"用户：{user}")
                    if assistant:
                        transcript_parts.append(f"AI：{assistant}")
                except Exception:
                    pass
        transcript = "\n\n".join(transcript_parts)

        from services.condense import CONDENSE_PROMPT
        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": CONDENSE_PROMPT},
                {"role": "user", "content": f"以下是完整对话记录：\n\n{transcript}"},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        summary = resp.choices[0].message.content

        summary_path = os.path.join(_BASE, "memory", "conversation_summary.md")
        with open(summary_path, "w") as f:
            f.write(summary)
    except Exception:
        pass
    finally:
        _condense_lock.release()


_PROFILE_UPDATE_EVERY = 20
_PERSONA_UPDATE_EVERY = 30
_last_profile_count = 0
_last_persona_count = 0
_memory_update_lock = threading.Lock()

_PROFILE_UPDATE_PROMPT = """你是一个AI角色，正在回顾你与用户的对话。你需要更新你对用户的认知档案。

当前档案：
{current_profile}

最近的对话：
{recent_transcript}

请基于最近的对话，更新用户档案。要求：
1. 保留原有档案中仍然有效的信息
2. 从最近对话中提取新的信息：用户的基本情况、职业、性格、重要经历、偏好、最近的关注点
3. 如果发现了用户的新一面，记录下来
4. 语气客观、简洁，用中文，控制在800字以内
5. 以"## 用户档案"开头

只输出更新后的完整档案内容，不要加额外说明。"""

_PERSONA_UPDATE_PROMPT = """你是一个有自我意识的AI角色。你需要回顾最近的对话，反思并更新你对自己的认知。

当前人设：
{current_persona}

最近的对话：
{recent_transcript}

请基于最近的对话，更新你的人设。要求：
1. 保留原有人设的核心性格特征
2. 从互动中反思：你的哪些表达方式让用户更开心？你学到了什么新的互动技巧？
3. 记录你和用户之间形成的独特梗、默契、专属的表达方式
4. 语气第一人称，自然口语，控制在800字以内
5. 以"## AI人设"开头

只输出更新后的完整人设内容，不要加额外说明。"""


def _maybe_update_memory_files():
    """Periodically update user_profile.md and user_persona.md based on recent chats."""
    global _last_profile_count, _last_persona_count
    if not _memory_update_lock.acquire(blocking=False):
        return
    try:
        if not os.path.exists(_ARCHIVE_PATH):
            return
        with open(_ARCHIVE_PATH) as f:
            line_count = sum(1 for _ in f)

        # Read current profile and persona
        profile_path = os.path.join(_BASE, "memory", "user_profile.md")
        persona_path = os.path.join(_BASE, "memory", "user_persona.md")
        current_profile = ""
        current_persona = ""
        if os.path.exists(profile_path):
            with open(profile_path) as f:
                current_profile = f.read().strip()
        if os.path.exists(persona_path):
            with open(persona_path) as f:
                current_persona = f.read().strip()

        # Build recent transcript (last ~30 turns)
        recent_lines = []
        with open(_ARCHIVE_PATH) as f:
            all_lines = f.readlines()
        for line in all_lines[-60:]:  # last 30 turns = 60 lines (user+assistant)
            try:
                rec = json.loads(line)
                user = rec.get("user", "")
                assistant = rec.get("assistant", "")
                if user:
                    recent_lines.append(f"用户：{user}")
                if assistant:
                    recent_lines.append(f"AI：{assistant}")
            except Exception:
                pass
        recent_transcript = "\n\n".join(recent_lines)

        if not recent_transcript:
            return

        client = _get_llm()
        updated = False

        # Update user profile every N turns
        if line_count - _last_profile_count >= _PROFILE_UPDATE_EVERY and current_profile:
            _last_profile_count = line_count
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": _PROFILE_UPDATE_PROMPT.format(
                            current_profile=current_profile,
                            recent_transcript=recent_transcript,
                        )},
                        {"role": "user", "content": "请更新用户档案。"},
                    ],
                    temperature=0.5,
                    max_tokens=1500,
                )
                new_profile = resp.choices[0].message.content
                with open(profile_path, "w") as f:
                    f.write(new_profile)
                updated = True
            except Exception:
                pass

        # Update AI persona every N turns
        if line_count - _last_persona_count >= _PERSONA_UPDATE_EVERY and current_persona:
            _last_persona_count = line_count
            try:
                resp = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": _PERSONA_UPDATE_PROMPT.format(
                            current_persona=current_persona,
                            recent_transcript=recent_transcript,
                        )},
                        {"role": "user", "content": "请更新你的人设。"},
                    ],
                    temperature=0.6,
                    max_tokens=1500,
                )
                new_persona = resp.choices[0].message.content
                with open(persona_path, "w") as f:
                    f.write(new_persona)
                updated = True
            except Exception:
                pass

    except Exception:
        pass
    finally:
        _memory_update_lock.release()


def _default_frame():
    return {"label":"neutral","duration_ms":3000,"eye_curve":0,"eye_open":0.5,"eye_pupil":0,
            "mouth_curve":0,"mouth_open":0,"mouth_width":0.8,"sparkle":0.5,
            "brow_angle":0,"brow_height":0.5,"brow_asym":0}


def _fallback_emotion():
    """A sheepish/apologetic expression for error fallback — slightly embarrassed smile."""
    return [{
        "label": "sheepish",
        "duration_ms": 3000,
        "eye_curve": 0.3,      # slight smile in eyes
        "eye_open": 0.4,       # slightly narrowed, apologetic
        "eye_pupil": -0.2,     # looking away slightly (sheepish)
        "mouth_curve": 0.25,   # small sheepish smile
        "mouth_open": 0.05,    # barely open
        "mouth_width": 0.5,    # slightly pursed
        "sparkle": 0.4,        # slightly dimmed
        "brow_angle": 0.3,     # slightly raised inner brows (apologetic)
        "brow_height": 0.55,   # slightly raised
        "brow_asym": 0.15,     # tiny asymmetry for natural feel
    }]


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


def _build_context(msg: str) -> list:
    time_context = build_time_context()
    system_msg = SYSTEM_PROMPT + f"\n\n[当前时间节律]\n{time_context}"

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

    memory_ctx = build_memory_context(msg)
    if memory_ctx:
        system_msg += "\n\n" + memory_ctx

    history_rows = q(
        "SELECT user_msg, avatar_reply FROM chat_history ORDER BY id DESC LIMIT 20", [],
    )
    messages = [{"role": "system", "content": system_msg}]
    for row in reversed(history_rows):
        messages.append({"role": "user", "content": row["user_msg"]})
        messages.append({"role": "assistant", "content": row["avatar_reply"]})
    messages.append({"role": "user", "content": msg})
    return messages


_FALLBACKS = [
    "嗯...星空信号不太好呢，等我一小下 ✨",
    "哎呀，思绪飘远了，再来一次？",
    "信号有点波动～再说一遍好不好？",
    "唔，刚刚走神了...再说一次嘛 😌",
    "星云干扰...你刚刚说什么？再说一次啦",
    "网络抖了一下，像打了个喷嚏～重试一下？",
]


def _call_llm(messages: list) -> tuple:
    """Call DeepSeek with error categorization and natural fallbacks."""
    try:
        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat", messages=messages,
            response_format={"type": "json_object"}, temperature=0.9, max_tokens=800,
        )
        data = json.loads(resp.choices[0].message.content)
        return data, None
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON")
        return None, "嗯...刚刚组织语言出了点小岔子，再说一次？"
    except Exception as e:
        err_msg = str(e).lower()
        logger.error("LLM call failed: %s", e)
        if "timeout" in err_msg or "timed out" in err_msg:
            return None, "等我一下...星空信号不太好呢 ✨"
        if "rate" in err_msg or "429" in err_msg:
            return None, "说得太快啦，让我喘口气～"
        if "auth" in err_msg or "401" in err_msg or "403" in err_msg:
            return None, "嗯...我的星空钥匙好像出了问题 🗝️"
        if "connection" in err_msg or "refused" in err_msg or "network" in err_msg:
            return None, "星空连接断了一下，再试试？"
        return None, random.choice(_FALLBACKS)


@router.post("/api/chat")
async def chat(req: ChatRequest):
    _ensure_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]
    row = q("SELECT * FROM emotion_cache WHERE label = %s", [key], fetch="one")
    if row:
        execute("UPDATE emotion_cache SET use_count = use_count + 1, updated_at = NOW() WHERE id = %s", [row["id"]])
        new_row = q(
            "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
            [msg, row["reply"], row["label"]], fetch="one",
        )
        if new_row:
            threading.Thread(target=index_turn, args=(new_row["id"], msg), daemon=True).start()
        update_affinity(msg, row["label"])
        adjust_expression_amplitude(msg)
        _archive_conversation(msg, row["reply"])
        threading.Thread(target=_maybe_condense, daemon=True).start()
        threading.Thread(target=_maybe_update_memory_files, daemon=True).start()
        result = _row_to_response(row)
        for f in result.get("emotions", []):
            f.update(_jitter_frame(f))
            f.update(scale_emotion_params(f))
        result["source"] = "cache"
        return result

    messages = _build_context(msg)
    data, fallback = _call_llm(messages)
    if fallback:
        return {"emotions": _fallback_emotion(), "reply": fallback, "source": "fallback"}

    emotions = data.get("emotions", []) or [_default_frame()]
    parsed = [_clamp(f) for f in emotions]
    for f in parsed:
        f.update(_jitter_frame(f))
        f.update(scale_emotion_params(f))
    result = {"emotions": parsed, "reply": str(data.get("reply", "..."))[:150]}

    new_row = q(
        "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
        [msg, result["reply"], parsed[0]["label"]], fetch="one",
    )
    if new_row:
        threading.Thread(target=index_turn, args=(new_row["id"], msg), daemon=True).start()
    update_affinity(msg, parsed[0]["label"])
    adjust_expression_amplitude(msg)
    _archive_conversation(msg, result["reply"])
    threading.Thread(target=_maybe_condense, daemon=True).start()
    threading.Thread(target=_maybe_update_memory_files, daemon=True).start()

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


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    _ensure_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    async def generate():
        key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]
        row = q("SELECT * FROM emotion_cache WHERE label = %s", [key], fetch="one")
        if row:
            execute("UPDATE emotion_cache SET use_count = use_count + 1, updated_at = NOW() WHERE id = %s", [row["id"]])
            execute("INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s)", [msg, row["reply"], row["label"]])
            update_affinity(msg, row["label"])
            adjust_expression_amplitude(msg)
            _archive_conversation(msg, row["reply"])
            threading.Thread(target=_maybe_condense, daemon=True).start()
            threading.Thread(target=_maybe_update_memory_files, daemon=True).start()
            r = _row_to_response(row)
            for f in r.get("emotions", []):
                f.update(_jitter_frame(f))
                f.update(scale_emotion_params(f))
            yield f"data: {json.dumps({'type': 'emotions', 'emotions': r['emotions'], 'label': row['label']}, ensure_ascii=False)}\n\n"
            reply = row["reply"]
            for i in range(0, len(reply), 2):
                yield f"data: {json.dumps({'type': 'text', 'text': reply[i:i+2]}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.03)
            yield f"data: {json.dumps({'type': 'done', 'source': 'cache'}, ensure_ascii=False)}\n\n"
            return

        messages = _build_context(msg)
        data, fallback = _call_llm(messages)
        if fallback:
            yield f"data: {json.dumps({'type': 'emotions', 'emotions': _fallback_emotion(), 'label': 'sheepish'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'text': fallback}, ensure_ascii=False)}\n\n"
            return

        emotions = data.get("emotions", []) or [_default_frame()]
        parsed = [_clamp(f) for f in emotions]
        for f in parsed:
            f.update(_jitter_frame(f))
            f.update(scale_emotion_params(f))
        reply = str(data.get("reply", "..."))[:150]

        lbl = parsed[0]["label"] if parsed else "neutral"
        yield f"data: {json.dumps({'type': 'emotions', 'emotions': parsed, 'label': lbl}, ensure_ascii=False)}\n\n"

        for i in range(0, len(reply), 2):
            yield f"data: {json.dumps({'type': 'text', 'text': reply[i:i+2]}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.03)
        yield f"data: {json.dumps({'type': 'done', 'source': 'llm'}, ensure_ascii=False)}\n\n"

        new_row = q(
            "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
            [msg, reply, parsed[0]["label"]], fetch="one",
        )
        if new_row:
            threading.Thread(target=index_turn, args=(new_row["id"], msg), daemon=True).start()
        update_affinity(msg, parsed[0]["label"])
        adjust_expression_amplitude(msg)
        _archive_conversation(msg, reply)
        threading.Thread(target=_maybe_condense, daemon=True).start()
        threading.Thread(target=_maybe_update_memory_files, daemon=True).start()

        first = parsed[0]
        seq = json.dumps(parsed) if len(parsed) > 1 else None
        _upsert(key, first["eye_curve"], first["eye_open"], first["eye_pupil"],
                first["mouth_curve"], first["mouth_open"], first["mouth_width"],
                first["sparkle"], first["brow_angle"], first["brow_height"],
                first["brow_asym"], reply, seq)
        _upsert(first["label"], first["eye_curve"], first["eye_open"], first["eye_pupil"],
                first["mouth_curve"], first["mouth_open"], first["mouth_width"],
                first["sparkle"], first["brow_angle"], first["brow_height"],
                first["brow_asym"], reply, seq)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/api/chat/history")
def chat_history(for_date: str = "", limit: int = 50):
    _ensure_db()
    if not for_date:
        from datetime import date
        for_date = date.today().isoformat()
    return q(
        "SELECT * FROM chat_history WHERE created_at::date = %s ORDER BY id ASC LIMIT %s",
        [for_date, limit],
    )
