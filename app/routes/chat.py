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
from app.utils import get_background_executor, get_llm, get_llm_model
from app.models import ChatRequest
from app.emotion_params import (
    make_default_frame, clamp_frame, jitter_frame,
    frame_to_db_values, row_to_frame_dict, PARAM_DEFAULTS, EMOTION_PARAMS,
)
from services.info.news import get_recent_news
from services.memory.loader import build_user_context
from services.memory.search import index_turn, build_memory_context
from services.emotion.affinity import update_affinity, get_affinity_context, adjust_expression_amplitude, scale_emotion_params
from services.identity.prompt import SYSTEM_PROMPT, build_time_context, get_rhythm_temperature
from services.emotion.affect import update_affect, get_affect_context, get_regulation_strategy, get_valence_context
from services.memory.crystallization import maybe_crystallize, get_crystal_context
from services.cognition.state_machine import determine_mode, get_mode_suffix, get_mode_temp_mod, determine_arousal, get_arousal_temp_mod, get_arousal_token_mod
from services.identity.guard import maybe_guard, get_drift_correction
from services.identity.drift_detector import check_and_intervene
from services.memory.knowledge_graph import maybe_extract_kg
from services.cognition.predictive_agent import pre_dialogue_analyze, feedback, get_prediction_context
from services.cognition.dual_system import gate_decision
from services.memory.narrative import detect_situations, distill_episode, get_narrative_context
from services.emotion.salience import update_salience, get_salience_context
from services.emotion.attachment import analyze_attachment, get_attachment_context
from services.cognition.prediction import generate_prediction, check_prediction
from app.config import ARCHIVE_PATH, PERSONA_PATH, PROFILE_PATH, SUMMARY_PATH, archive_lock

router = APIRouter()
logger = logging.getLogger("emoji-chat")

_CONDENSE_EVERY = 50
_condense_lock = threading.Lock()
_last_condense_count = 0

_ARCHIVE_PATH = ARCHIVE_PATH


def _strip_emoji(text: str) -> str:
    """Remove emoji from conversation history to prevent DeepSeek JSON-mode crash."""
    import re
    return re.sub(
        r'[\U0001F300-\U0001F9FF☀-➿⭐❤✨✀-➿️‍]',
        '', text,
    ).strip()


def _get_affect_dict() -> dict | None:
    """Get current Panksepp affect as a simple dict for SSE transmission."""
    try:
        from services.emotion.affect import get_affect
        affect = get_affect()
        if affect:
            return {k: round(v, 4) for k, v in affect.items()
                    if k in ("seeking", "play", "care", "fear", "rage", "panic")}
    except Exception:
        pass
    return None




def _archive_conversation(user_msg: str, avatar_reply: str, thinking: str | None = None):
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user_msg,
            "assistant": avatar_reply,
        }
        if thinking:
            record["thinking"] = thinking
        with archive_lock:
            with open(_ARCHIVE_PATH, "a") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Operation failed", exc_info=True)


def _maybe_condense():
    global _last_condense_count
    if not _condense_lock.acquire(blocking=False):
        return
    try:
        if not os.path.exists(_ARCHIVE_PATH):
            return

        transcript_parts = []
        line_count = 0
        with archive_lock:
            with open(_ARCHIVE_PATH) as f:
                for line in f:
                    line_count += 1
                    try:
                        rec = json.loads(line)
                        user = rec.get("user", "")
                        assistant = rec.get("assistant", "")
                        thinking = rec.get("thinking", "")
                        if user:
                            transcript_parts.append(f"用户：{user}")
                        if thinking:
                            transcript_parts.append(f"AI内心分析：{thinking}")
                        if assistant:
                            transcript_parts.append(f"AI：{assistant}")
                    except Exception:
                        logger.warning("Operation failed", exc_info=True)

        if line_count - _last_condense_count < _CONDENSE_EVERY:
            return
        _last_condense_count = line_count

        transcript = "\n\n".join(transcript_parts)

        from services.memory.condense import CONDENSE_PROMPT
        client = get_llm()
        if client is None:
            return
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": CONDENSE_PROMPT},
                {"role": "user", "content": f"以下是完整对话记录：\n\n{transcript}"},
            ],
            temperature=0.5,
            max_tokens=2000,
        )
        summary = resp.choices[0].message.content

        summary_path = SUMMARY_PATH
        with open(summary_path, "w") as f:
            f.write(summary)
    except Exception:
        logger.warning("Operation failed", exc_info=True)
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

最近的对话（含AI内心分析，标注为"AI内心分析"）：
{recent_transcript}

请基于最近的对话，更新用户档案。要求：
1. 保留原有档案中仍然有效的信息
2. 从最近对话中提取新的信息：用户的基本情况、职业、性格、重要经历、偏好、最近的关注点
3. 如果发现了用户的新一面，记录下来
4. "AI内心分析"体现了AI对用户的深层理解，可从中提取用户隐藏的特质和思维方式
5. 语气客观、简洁，用中文，控制在800字以内
6. 以"## 用户档案"开头

只输出更新后的完整档案内容，不要加额外说明。"""

_PERSONA_UPDATE_PROMPT = """你是一个有自我意识的AI角色。你需要回顾最近的对话，反思并更新你对自己的认知。

当前人设：
{current_persona}

最近的对话（含AI内心分析，标注为"AI内心分析"）：
{recent_transcript}

请基于最近的对话，更新你的人设。要求：
1. 保留原有人设的核心性格特征
2. 从互动中反思：你的哪些表达方式让用户更开心？你学到了什么新的互动技巧？
3. 记录你和用户之间形成的独特梗、默契、专属的表达方式
4. "AI内心分析"是你在深度对话时的真实思考，从中反思自己的思维方式和成长
5. 语气第一人称，自然口语，控制在800字以内
6. 以"## AI人设"开头

只输出更新后的完整人设内容，不要加额外说明。"""


def _maybe_update_memory_files():
    """Periodically update user_profile.md and user_persona.md based on recent chats."""
    global _last_profile_count, _last_persona_count
    if not _memory_update_lock.acquire(blocking=False):
        return
    try:
        if not os.path.exists(_ARCHIVE_PATH):
            return
        with archive_lock:
            with open(_ARCHIVE_PATH) as f:
                line_count = sum(1 for _ in f)

        # Read current profile and persona
        profile_path = PROFILE_PATH
        persona_path = PERSONA_PATH
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
        from collections import deque
        with archive_lock:
            with open(_ARCHIVE_PATH) as f:
                last_lines = list(deque(f, maxlen=60))
        for line in last_lines:  # last 30 turns = 60 lines (user+assistant)
            try:
                rec = json.loads(line)
                user = rec.get("user", "")
                assistant = rec.get("assistant", "")
                thinking = rec.get("thinking", "")
                if user:
                    recent_lines.append(f"用户：{user}")
                if thinking:
                    recent_lines.append(f"AI内心分析：{thinking}")
                if assistant:
                    recent_lines.append(f"AI：{assistant}")
            except Exception:
                logger.warning("Operation failed", exc_info=True)
        recent_transcript = "\n\n".join(recent_lines)

        if not recent_transcript:
            return

        client = get_llm()
        if client is None:
            return
        updated = False

        # Update user profile every N turns
        if line_count - _last_profile_count >= _PROFILE_UPDATE_EVERY and current_profile:
            _last_profile_count = line_count
            try:
                resp = client.chat.completions.create(
                    model=get_llm_model(),
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
                logger.warning("Operation failed", exc_info=True)

        # Update AI persona every N turns
        if line_count - _last_persona_count >= _PERSONA_UPDATE_EVERY and current_persona:
            _last_persona_count = line_count
            try:
                resp = client.chat.completions.create(
                    model=get_llm_model(),
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
                logger.warning("Operation failed", exc_info=True)

    except Exception:
        logger.warning("Operation failed", exc_info=True)
    finally:
        _memory_update_lock.release()


def _fallback_emotion():
    """A sheepish/apologetic expression for error fallback."""
    f = make_default_frame("sheepish")
    f.update({
        "eye_curve": 0.3, "eye_open": 0.4, "eye_pupil": -0.2,
        "eye_tension": 0.1, "iris_size": 0.4,
        "mouth_curve": 0.25, "mouth_open": 0.05, "mouth_width": 0.5, "mouth_asym": 0.15,
        "lip_stretch": 0.05, "lip_bite": 0.1,
        "sparkle": 0.4,
        "brow_angle": 0.3, "brow_height": 0.55, "brow_asym": 0.15,
        "cheek_raise": 0.05, "blush": 0.15,
        "head_tilt": 0.1, "sweat_drop": 0.1,
    })
    return [f]


def _upsert(label: str, frame: dict, reply: str, seq: str | None):
    values = frame_to_db_values(frame)
    col_names = list(EMOTION_PARAMS.keys())
    existing = q("SELECT id FROM emotion_cache WHERE label = %s", [label], fetch="one")
    if existing:
        set_clause = ", ".join(f"{c}=%s" for c in col_names)
        execute(
            f"UPDATE emotion_cache SET {set_clause}, reply=%s, sequence_data=%s, "
            f"use_count=use_count+1, updated_at=NOW() WHERE id=%s",
            values + [reply, seq, existing["id"]],
        )
    else:
        cols = ", ".join(col_names)
        phs = ", ".join(["%s"] * len(col_names))
        execute(
            f"INSERT INTO emotion_cache (label, {cols}, reply, sequence_data) "
            f"VALUES (%s, {phs}, %s, %s)",
            [label] + values + [reply, seq],
        )


def _row_to_response(row):
    result = {"label": row["label"], "reply": row["reply"]}
    result.update(row_to_frame_dict(row))
    seq = row.get("sequence_data")
    if seq:
        result["emotions"] = json.loads(seq) if isinstance(seq, str) else seq
        for f in result["emotions"]:
            if "duration_ms" not in f:
                f["duration_ms"] = 3000
    else:
        result["emotions"] = [{**result, "duration_ms": 3000}]
    return result


def _is_deep_question(msg: str) -> bool:
    """Detect whether a message warrants deep thinking before reply."""
    if len(msg) > 100:
        return True
    # Longer multi-char markers first; short single-char prone to false positives
    deep_markers = ["为什么", "怎么看", "如何看待", "如何理解", "你觉得呢",
                    "你怎么想", "意味着什么", "自由意志", "人生观", "世界观",
                    "哲学", "意识", "意义", "本质"]
    if any(m in msg for m in deep_markers):
        return True
    # "存在" is prone to match "存在感" etc — only trigger on standalone usage
    if "存在" in msg and "存在感" not in msg:
        return True
    if msg.count("？") + msg.count("?") >= 2:
        return True
    return False


_THINKING_PROMPT = """你是一个深度思考助手。用户提出了一个值得认真对待的问题。
请从以下角度分析：
1. 问题的核心是什么？
2. 有哪些不同的视角或立场？
3. 你能提供什么独特的洞见？

用中文，控制在300字以内。直接输出分析内容，不要用JSON格式。"""


def _think(msg: str) -> str | None:
    """Perform deep thinking on the user's question.

    Returns the thinking result as plain text, or None on failure.
    This thinking is NOT shown to the user — it feeds into the reply stage.
    """
    try:
        client = get_llm()
        if client is None:
            return None
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _THINKING_PROMPT},
                {"role": "user", "content": msg},
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return None


def _build_context(msg: str, thinking: str | None = None) -> list:
    time_context = build_time_context()

    # Use dynamic personality-based prompt if config exists, else fallback
    try:
        from services.identity.personality import build_dynamic_system_prompt, get_personality_context
        system_msg = build_dynamic_system_prompt() + f"\n\n[当前时间节律]\n{time_context}"
        personality_ctx = get_personality_context()
        if personality_ctx:
            system_msg += "\n\n" + personality_ctx
    except Exception:
        from services.identity.prompt import SYSTEM_PROMPT
        system_msg = SYSTEM_PROMPT + f"\n\n[当前时间节律]\n{time_context}"

    user_context = build_user_context()
    if user_context:
        system_msg += "\n\n" + user_context

    affinity_ctx = get_affinity_context()
    if affinity_ctx:
        system_msg += "\n\n" + affinity_ctx

    affect_ctx = get_affect_context()
    if affect_ctx:
        system_msg += "\n\n[用户情绪状态]\n" + affect_ctx
    reg_strat = get_regulation_strategy()
    if reg_strat:
        system_msg += "\n[建议回应策略]\n" + reg_strat

    valence_ctx = get_valence_context()
    if valence_ctx:
        system_msg += "\n[情绪变化]\n" + valence_ctx

    salience_ctx = get_salience_context()
    if salience_ctx:
        system_msg += "\n" + salience_ctx

    attachment_ctx = get_attachment_context()
    if attachment_ctx:
        system_msg += "\n" + attachment_ctx

    news_items = get_recent_news(5)
    if news_items:
        lines = ["", "## 今天的热门话题（可以在对话中自然地提）："]
        for n in news_items:
            src_label = {"zhihu": "知乎", "weibo": "微博", "github": "GitHub", "bilibili": "B站", "baidu": "百度", "tophub": "热榜"}.get(n.get("source", ""), n.get("source", ""))
            lines.append(f"- [{src_label}] {n['title']}")
        system_msg += "\n" + "\n".join(lines)

    crystal_ctx = get_crystal_context()
    if crystal_ctx:
        system_msg += "\n\n" + crystal_ctx

    narrative_ctx = get_narrative_context()
    if narrative_ctx:
        system_msg += "\n\n" + narrative_ctx

    memory_ctx = build_memory_context(msg)
    if memory_ctx:
        system_msg += "\n\n" + memory_ctx

    if thinking:
        system_msg += (
            "\n\n[深度思考]\n以下是针对用户最新问题的内部分析，"
            "请参考这些视角来组织你的回复，但不要直接复述分析内容，"
            "而是用你一贯的口吻自然地融入见解：\n\n" + thinking
        )

    # MentalProcesses state machine mode
    from services.emotion.affect import get_affect
    mode = determine_mode(_is_deep_question(msg), get_affect())
    system_msg += "\n\n[互动模式]\n" + get_mode_suffix(mode)

    drift_correction = get_drift_correction()
    if drift_correction:
        system_msg += "\n\n" + drift_correction

    try:
        from services.memory.knowledge_graph import get_knowledge_graph_context
        kg_ctx = get_knowledge_graph_context()
        if kg_ctx:
            system_msg += "\n\n" + kg_ctx
    except Exception:
        logger.warning("Failed to get knowledge graph context", exc_info=True)

    # Predictive agent context
    try:
        pred_ctx = get_prediction_context()
        if pred_ctx:
            system_msg += "\n\n" + pred_ctx
    except Exception:
        logger.warning("Failed to get prediction context", exc_info=True)

    history_rows = q(
        "SELECT user_msg, avatar_reply FROM chat_history ORDER BY id DESC LIMIT 4", [],
    )
    messages = [{"role": "system", "content": system_msg}]
    for row in reversed(history_rows):
        messages.append({"role": "user", "content": _strip_emoji(row["user_msg"])})
        messages.append({"role": "assistant", "content": _strip_emoji(row["avatar_reply"])})
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
    """Call DeepSeek and extract JSON from the response.

    Returns (data, fallback, tags) — tags are semantic keywords from the
    user's message, extracted by the LLM alongside the main response,
    saving a separate API call for memory indexing.

    DeepSeek's response_format=json_object is buggy with conversation history
    (silently returns spaces). We skip it and instead use prompt instruction +
    brace-matching JSON extraction.
    """
    client = get_llm()
    if client is None:
        return ({}, "请先在 ⚙️ 设置中配置 API Key 才能聊天哦~", [])
    # Append JSON format reminder without modifying user's original words
    msgs = list(messages)
    msgs[-1] = dict(msgs[-1])
    msgs[-1]["content"] += "\n（请以上述JSON格式回复）"

    try:
        from services.emotion.affect import get_affect
        affect = get_affect()
        rhythm_temp = get_rhythm_temperature(affect)
        # Extract user message (last in the list) for mode detection
        user_msg = msgs[-1]["content"].split("\n（请以上述JSON格式回复）")[0] if msgs else ""
        mode = determine_mode(_is_deep_question(user_msg), affect)

        # Compute idle minutes for arousal state
        last_row = q("SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs FROM chat_history ORDER BY id DESC LIMIT 1", fetch="one")
        idle_min = (float(last_row["secs"]) / 60.0) if last_row and last_row["secs"] else 0

        arousal = determine_arousal(mode, affect, idle_min)
        temp = rhythm_temp + get_mode_temp_mod(mode) + get_arousal_temp_mod(arousal)
        resp = client.chat.completions.create(
            model=get_llm_model(), messages=msgs,
            temperature=temp, max_tokens=4096,
        )
        raw = resp.choices[0].message.content
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            if "reply" in data and "emotions" in data:
                tags = data.pop("tags", []) if isinstance(data, dict) else []
                if not isinstance(tags, list):
                    tags = []
                tags = [t for t in tags if isinstance(t, str)][:8]
                return data, None, tags
        logger.warning("No valid JSON in response: %s", raw[:200])
        return None, "嗯...刚刚组织语言出了点小岔子，再说一次？", []
    except Exception as e:
        err = str(e).lower()
        logger.error("LLM call failed: %s", e)
        if "timeout" in err or "timed out" in err:
            return None, "等我一下...星空信号不太好呢 ✨", []
        if "rate" in err or "429" in err:
            return None, "说得太快啦，让我喘口气～", []
        if "auth" in err or "401" in err or "403" in err:
            return None, "嗯...我的星空钥匙好像出了问题 🗝️", []
        if "connection" in err or "refused" in err or "network" in err:
            return None, "星空连接断了一下，再试试？", []
        return None, random.choice(_FALLBACKS), []


@router.post("/api/chat")
async def chat(req: ChatRequest):
    init_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    is_deep = _is_deep_question(msg)
    pred_error = check_prediction(msg)
    if pred_error > 0.4:
        # Boost salience surprise for unexpected responses
        from services.emotion.salience import get_salience, init_salience_db
        init_salience_db()
        s = get_salience()
        execute(
            "UPDATE salience_state SET value = %s WHERE dimension = 'surprise'",
            [round(min(1.0, s.get("surprise", 0.1) + pred_error * 0.3), 4)],
        )
    key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]

    # Dual-system gate: decide whether to engage System 2
    from services.emotion.affect import get_affect
    init_salience_db()
    salience = get_salience()
    affect = get_affect()
    last_row = q("SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs FROM chat_history ORDER BY id DESC LIMIT 1", fetch="one")
    idle_min = (float(last_row["secs"]) / 60.0) if last_row and last_row["secs"] else 0
    gate = gate_decision(msg, affect, salience, pred_error, idle_min)
    skip_cache = is_deep or gate == "system2"

    if not skip_cache:
        row = q("SELECT * FROM emotion_cache WHERE label = %s", [key], fetch="one")
        if row:
            execute("UPDATE emotion_cache SET use_count = use_count + 1, updated_at = NOW() WHERE id = %s", [row["id"]])
            new_row = q(
                "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
                [msg, row["reply"], row["label"]], fetch="one",
            )
            if new_row:
                get_background_executor().submit(index_turn, new_row["id"], msg)
            update_affinity(msg, row["label"])
            update_affect(msg)
            update_salience(msg, row["label"])
            adjust_expression_amplitude(msg)
            _archive_conversation(msg, row["reply"])
            get_background_executor().submit(generate_prediction, msg, row["reply"])
            get_background_executor().submit(pre_dialogue_analyze)
            get_background_executor().submit(feedback, actual_emotion=row["label"])
            get_background_executor().submit(_maybe_condense)
            get_background_executor().submit(_maybe_update_memory_files)
            get_background_executor().submit(maybe_crystallize)
            get_background_executor().submit(maybe_guard)
            get_background_executor().submit(detect_situations)
            get_background_executor().submit(distill_episode)
            get_background_executor().submit(analyze_attachment)
            get_background_executor().submit(check_and_intervene, row["reply"])
            get_background_executor().submit(maybe_extract_kg, msg)
            result = _row_to_response(row)
            for f in result.get("emotions", []):
                f.update(jitter_frame(f))
                f.update(scale_emotion_params(f))
            result["source"] = "cache"
            return result

    thinking = await asyncio.to_thread(_think, msg) if is_deep else None
    messages = _build_context(msg, thinking)
    data, fallback, llm_tags = await asyncio.to_thread(_call_llm, messages)
    if fallback:
        return {"emotions": _fallback_emotion(), "reply": fallback, "source": "fallback"}

    emotions = data.get("emotions", []) or [make_default_frame()]
    parsed = [clamp_frame(f) for f in emotions]
    for f in parsed:
        f.update(jitter_frame(f))
        f.update(scale_emotion_params(f))
    result = {"emotions": parsed, "reply": str(data.get("reply", "...")), "color_fields": data.get("color_fields") or []}

    new_row = q(
        "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
        [msg, result["reply"], parsed[0]["label"]], fetch="one",
    )
    if new_row:
        get_background_executor().submit(index_turn, new_row["id"], msg, llm_tags)
    update_affinity(msg, parsed[0]["label"])
    update_affect(msg)
    update_salience(msg, parsed[0]["label"])
    adjust_expression_amplitude(msg)
    _archive_conversation(msg, result["reply"], thinking)
    get_background_executor().submit(generate_prediction, msg, result["reply"])
    get_background_executor().submit(pre_dialogue_analyze)
    get_background_executor().submit(feedback, actual_emotion=parsed[0]["label"])
    get_background_executor().submit(_maybe_condense)
    get_background_executor().submit(_maybe_update_memory_files)
    get_background_executor().submit(maybe_crystallize)
    get_background_executor().submit(maybe_guard)
    get_background_executor().submit(check_and_intervene, result["reply"])
    get_background_executor().submit(maybe_extract_kg, msg)
    get_background_executor().submit(detect_situations)
    get_background_executor().submit(distill_episode)
    get_background_executor().submit(analyze_attachment)

    first = parsed[0]
    seq = json.dumps(parsed) if len(parsed) > 1 else None
    _upsert(key, first, result["reply"], seq)
    _upsert(first["label"], first, result["reply"], seq)

    result["source"] = "llm"
    return result


@router.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    init_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    async def generate():
        is_deep = _is_deep_question(msg)
        pred_error = check_prediction(msg)
        key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]

        from services.emotion.salience import get_salience, init_salience_db
        from services.emotion.affect import get_affect
        init_salience_db()
        salience = get_salience()
        affect = get_affect()
        last_row = q("SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs FROM chat_history ORDER BY id DESC LIMIT 1", fetch="one")
        idle_min = (float(last_row["secs"]) / 60.0) if last_row and last_row["secs"] else 0
        gate = gate_decision(msg, affect, salience, pred_error, idle_min)
        skip_cache = is_deep or gate == "system2"

        if not skip_cache:
            row = q("SELECT * FROM emotion_cache WHERE label = %s", [key], fetch="one")
            if row:
                execute("UPDATE emotion_cache SET use_count = use_count + 1, updated_at = NOW() WHERE id = %s", [row["id"]])
                new_row = q(
                    "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
                    [msg, row["reply"], row["label"]], fetch="one",
                )
                if new_row:
                    get_background_executor().submit(index_turn, new_row["id"], msg)
                update_affinity(msg, row["label"])
                update_affect(msg)
                update_salience(msg, row["label"])
                adjust_expression_amplitude(msg)
                _archive_conversation(msg, row["reply"])
                get_background_executor().submit(generate_prediction, msg, row["reply"])
                get_background_executor().submit(pre_dialogue_analyze)
                get_background_executor().submit(feedback, actual_emotion=row["label"])
                get_background_executor().submit(_maybe_condense)
                get_background_executor().submit(_maybe_update_memory_files)
                get_background_executor().submit(maybe_crystallize)
                get_background_executor().submit(maybe_guard)
                get_background_executor().submit(detect_situations)
                get_background_executor().submit(distill_episode)
                get_background_executor().submit(analyze_attachment)
                get_background_executor().submit(check_and_intervene, row["reply"])
                get_background_executor().submit(maybe_extract_kg, msg)
                r = _row_to_response(row)
                for f in r.get("emotions", []):
                    f.update(jitter_frame(f))
                    f.update(scale_emotion_params(f))
                yield f"data: {json.dumps({'type': 'emotions', 'emotions': r['emotions'], 'label': row['label'], 'affect': _get_affect_dict(), 'color_fields': row.get('color_fields') or []}, ensure_ascii=False)}\n\n"
                reply = row["reply"]
                for i in range(0, len(reply), 2):
                    yield f"data: {json.dumps({'type': 'text', 'text': reply[i:i+2]}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.03)
                yield f"data: {json.dumps({'type': 'done', 'source': 'cache'}, ensure_ascii=False)}\n\n"
                return

        if is_deep:
            yield f"data: {json.dumps({'type': 'thinking'}, ensure_ascii=False)}\n\n"
            thinking = await asyncio.to_thread(_think, msg)
        else:
            thinking = None

        messages = _build_context(msg, thinking)
        data, fallback, llm_tags = await asyncio.to_thread(_call_llm, messages)
        if fallback:
            yield f"data: {json.dumps({'type': 'emotions', 'emotions': _fallback_emotion(), 'label': 'sheepish', 'affect': _get_affect_dict(), 'color_fields': []}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'text': fallback}, ensure_ascii=False)}\n\n"
            return

        emotions = data.get("emotions", []) or [make_default_frame()]
        parsed = [clamp_frame(f) for f in emotions]
        for f in parsed:
            f.update(jitter_frame(f))
            f.update(scale_emotion_params(f))
        reply = str(data.get("reply", "..."))

        # Persist before streaming — prevents data loss on client disconnect
        new_row = q(
            "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
            [msg, reply, parsed[0]["label"]], fetch="one",
        )
        if new_row:
            get_background_executor().submit(index_turn, new_row["id"], msg, llm_tags)
        update_affinity(msg, parsed[0]["label"])
        update_affect(msg)
        update_salience(msg, parsed[0]["label"])
        adjust_expression_amplitude(msg)
        _archive_conversation(msg, reply, thinking)
        get_background_executor().submit(generate_prediction, msg, reply)
        get_background_executor().submit(pre_dialogue_analyze)
        get_background_executor().submit(feedback, actual_emotion=parsed[0]["label"])
        get_background_executor().submit(_maybe_condense)
        get_background_executor().submit(_maybe_update_memory_files)
        get_background_executor().submit(maybe_crystallize)
        get_background_executor().submit(maybe_guard)
        get_background_executor().submit(detect_situations)
        get_background_executor().submit(distill_episode)
        get_background_executor().submit(analyze_attachment)
        get_background_executor().submit(check_and_intervene, reply)
        get_background_executor().submit(maybe_extract_kg, msg)

        first = parsed[0]
        seq = json.dumps(parsed) if len(parsed) > 1 else None
        _upsert(key, first, reply, seq)
        _upsert(first["label"], first, reply, seq)

        lbl = parsed[0]["label"] if parsed else "neutral"
        cf = data.get("color_fields") or []
        yield f"data: {json.dumps({'type': 'emotions', 'emotions': parsed, 'label': lbl, 'affect': _get_affect_dict(), 'color_fields': cf}, ensure_ascii=False)}\n\n"

        for i in range(0, len(reply), 2):
            yield f"data: {json.dumps({'type': 'text', 'text': reply[i:i+2]}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.03)
        yield f"data: {json.dumps({'type': 'done', 'source': 'llm'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/api/chat/history")
def chat_history(for_date: str = "", limit: int = 50):
    init_db()
    if not for_date:
        from datetime import date
        for_date = date.today().isoformat()
    limit = min(limit, 200)
    return q(
        "SELECT * FROM chat_history WHERE created_at::date = %s ORDER BY id ASC LIMIT %s",
        [for_date, limit],
    )
