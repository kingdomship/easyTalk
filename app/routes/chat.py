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
from app.utils import get_background_executor, get_llm, get_llm_model, llm_foreground, llm_foreground_clear
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
from services.identity.sprite_prompt import SPRITE_SYSTEM_PROMPT, build_sprite_user_prompt
from services.identity.sprite_library import lookup_sprite, persist_sprite
from services.emotion.affect import update_affect, get_affect_context, get_valence_context
from services.memory.crystallization import maybe_crystallize, get_crystal_context
from services.cognition.state_machine import determine_mode, get_mode_suffix, get_mode_temp_mod, determine_arousal, get_arousal_temp_mod, get_arousal_token_mod, get_drive_temp_mod
from services.identity.guard import maybe_guard, get_drift_correction
from services.identity.drift_detector import check_and_intervene
from services.memory.knowledge_graph import maybe_extract_kg
from services.cognition.predictive_agent import pre_dialogue_analyze, feedback, get_prediction_context
from services.cognition.dual_system import gate_decision, self_evaluate, maybe_deep_audit, get_self_eval_correction
from services.memory.narrative import detect_situations, distill_episode, get_narrative_context
from services.emotion.salience import update_salience, get_salience_context
from services.emotion.attachment import analyze_attachment, get_attachment_context
from services.cognition.prediction import generate_prediction, check_prediction
from services.drive.engine import update_drives_on_chat, get_drive_context, get_drive_values
from services.therapy.crisis import crisis_keyword_check, crisis_llm_verify, get_crisis_context, log_crisis_event, update_risk_snapshot
from services.therapy.intent import analyze_therapy_intent, get_therapy_modules
from services.therapy.modules import assemble_therapy_modules
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


def _post_reply_pipeline(msg: str, reply: str, label: str,
                         thinking: str | None = None,
                         llm_tags: list[str] | None = None,
                         turn_id: int | None = None,
                         is_deep: bool = False,
                         crisis_result: dict | None = None):
    """Unified post-reply pipeline: index, update state, archive, fire background tasks."""
    # ── 危机事件日志 ──────────────────────────────────────────
    if crisis_result and crisis_result.get("severity", 0) > 0:
        try:
            log_crisis_event(msg, crisis_result)
        except Exception:
            logger.warning("危机事件记录失败", exc_info=True)
    # 风险快照更新 (每小时一次, 纯计算)
    try:
        update_risk_snapshot()
    except Exception:
        logger.warning("风险快照更新失败", exc_info=True)

    if turn_id is not None:
        if llm_tags:
            get_background_executor().submit(index_turn, turn_id, msg, llm_tags)
        else:
            get_background_executor().submit(index_turn, turn_id, msg)
    update_affinity(msg, label)
    update_affect(msg)
    update_salience(msg, label)

    # Life domain tracking + curiosity seeding (lightweight, no LLM)
    try:
        from services.psych.life_domains import update_life_domains
        from services.emotion.affect import get_affect
        update_life_domains(msg, get_affect())
    except Exception:
        logger.warning("生命领域更新失败", exc_info=True)
    try:
        from services.psych.entry_point import update_curiosity_queue
        update_curiosity_queue(msg)
    except Exception:
        logger.warning("好奇心队列更新失败", exc_info=True)
    adjust_expression_amplitude(msg)
    _archive_conversation(msg, reply, thinking)
    get_background_executor().submit(update_drives_on_chat, msg, label, is_deep=is_deep)
    get_background_executor().submit(generate_prediction, msg, reply)
    get_background_executor().submit(pre_dialogue_analyze)
    get_background_executor().submit(feedback, actual_emotion=label)
    get_background_executor().submit(_maybe_condense)
    get_background_executor().submit(_maybe_update_memory_files)
    get_background_executor().submit(maybe_crystallize)
    get_background_executor().submit(maybe_guard)
    get_background_executor().submit(detect_situations)
    get_background_executor().submit(distill_episode)
    get_background_executor().submit(analyze_attachment)
    get_background_executor().submit(check_and_intervene, reply)
    get_background_executor().submit(maybe_extract_kg, msg)
    get_background_executor().submit(self_evaluate, msg, reply, turn_id)
    get_background_executor().submit(maybe_deep_audit)


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
        _last_condense_count = line_count
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
                _last_profile_count = line_count
                updated = True
            except Exception:
                logger.warning("Operation failed", exc_info=True)

        # Update AI persona every N turns
        if line_count - _last_persona_count >= _PERSONA_UPDATE_EVERY and current_persona:
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
                _last_persona_count = line_count
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


def _upsert(label: str, frame: dict, reply: str, seq: str | None, color_fields: list | None = None, background: str | None = None, whiteboard: list | None = None):
    values = frame_to_db_values(frame)
    col_names = list(EMOTION_PARAMS.keys())
    cf_json = json.dumps(color_fields, ensure_ascii=False) if color_fields else None
    wb_json = json.dumps(whiteboard, ensure_ascii=False) if whiteboard else None
    existing = q("SELECT id FROM emotion_cache WHERE label = %s", [label], fetch="one")
    if existing:
        set_clause = ", ".join(f"{c}=%s" for c in col_names)
        execute(
            f"UPDATE emotion_cache SET {set_clause}, reply=%s, sequence_data=%s, "
            f"color_fields=%s, background=%s, whiteboard=%s, use_count=use_count+1, updated_at=NOW() WHERE id=%s",
            values + [reply, seq, cf_json, background, wb_json, existing["id"]],
        )
    else:
        cols = ", ".join(col_names)
        phs = ", ".join(["%s"] * len(col_names))
        execute(
            f"INSERT INTO emotion_cache (label, {cols}, reply, sequence_data, color_fields, background, whiteboard) "
            f"VALUES (%s, {phs}, %s, %s, %s, %s, %s)",
            [label] + values + [reply, seq, cf_json, background, wb_json],
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
    cf = row.get("color_fields")
    result["color_fields"] = json.loads(cf) if isinstance(cf, str) else (cf or [])
    result["background"] = row.get("background") or None
    wb = row.get("whiteboard")
    result["whiteboard"] = json.loads(wb) if isinstance(wb, str) else (wb or [])
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

_INTENT_PROMPT = """分析用户消息，输出模块配置JSON。

6个可选模块及用途：
- composite: 复合表情示例参考，情绪表达浓烈时用
- color_fields: 氛围光晕（Rothko风格色块），情绪/天气/话题场景时用
- background: 画布背景基调色，具体场景氛围时用
- sprites: 像素精灵动画（小图标从脸部飞出），对话中聊到/提及某个具体物品时点缀用（如"今天喝了咖啡"→☕精灵）。注意：用户明确说"画X"时不触发此模块
- whiteboard: 手绘线条/图形（line/circle/dot），用户明确要求"画个X"、"画一下"、或"画一个"某物时在画布上绘制。也适用于用户要求手绘/简笔画风格的场景
- scenes: 多段叙事（Freytag金字塔），明确要求讲故事时用

每个模块设为: "skip"(不需要) / "compact"(精简参数，仅格式说明) / "full"(完整指导，含详细示例)。
判断原则：根据消息内容精确评估哪些模块真正需要。日常闲聊全部skip。消息涉及到什么才开启什么，"compact"用于辅助氛围，"full"用于核心需求。
同时输出"tags"数组（3-8个中文关键词）和"creativity"(normal/high，需要叙事创意时用high)。
以及"batch_mode"布尔值：用户消息是否包含2个或以上明显独立的请求/问题（如"帮我查天气，顺便推荐一本好书"），需要分批次逐一回答。

输出格式：
{"modules":{"composite":"skip","color_fields":"compact","background":"skip","sprites":"skip","whiteboard":"skip","scenes":"skip"},"tags":["下雨","心情","低落"],"creativity":"normal","batch_mode":false}"""


def _analyze_intent_sync(msg: str) -> tuple[dict | None, list[str], str]:
    """Quick AI pre-analysis: returns per-module config, tags, and creativity level.

    Returns (modules_config, tags, creativity). On failure returns (None, [], "normal").
    When batch_mode is detected, forces scenes=full in modules_config and injects
    __batch_mode=True internal flag.
    """
    try:
        client = get_llm()
        if client is None:
            return None, [], "normal"
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": _INTENT_PROMPT},
                {"role": "user", "content": msg},
            ],
            temperature=0.0,
            max_tokens=150,
            timeout=10.0,
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            modules_config = data.get("modules") if isinstance(data.get("modules"), dict) else None
            tags = data.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            tags = [t for t in tags if isinstance(t, str)][:8]
            creativity = data.get("creativity", "normal")
            if creativity not in ("normal", "high"):
                creativity = "normal"
            # Multi-question batching: force scenes for batched mode
            if data.get("batch_mode") is True:
                if modules_config is None:
                    modules_config = {}
                modules_config["scenes"] = "full"
                modules_config["__batch_mode"] = True
            return modules_config, tags, creativity
    except Exception:
        logger.warning("Intent analysis failed, falling back to base prompt", exc_info=True)
    return None, [], "normal"


async def _analyze_intent(msg: str) -> tuple[dict | None, list[str], str]:
    """Async wrapper for _analyze_intent_sync."""
    return await asyncio.to_thread(_analyze_intent_sync, msg)


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
            timeout=30.0,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return None


def _build_context(msg: str, thinking: str | None = None,
                   modules_config: dict | None = None,
                   crisis_result: dict | None = None,
                   therapy_intent: dict | None = None) -> list:
    time_context = build_time_context()

    # Use dynamic personality-based prompt if config exists, else fallback
    try:
        from services.identity.personality import build_dynamic_system_prompt, get_personality_context
        system_msg = build_dynamic_system_prompt(msg=msg, modules_config=modules_config) + f"\n\n[当前时间节律]\n{time_context}"
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

    # ── 治疗模块注入 (按需, 在情绪上下文之前) ──────────────
    if therapy_intent and therapy_intent.get("intent") not in (None, "none"):
        therapy_prompt = assemble_therapy_modules(therapy_intent["intent"])
        if therapy_prompt:
            system_msg += "\n\n" + therapy_prompt

    affect_ctx = get_affect_context()
    if affect_ctx:
        system_msg += "\n\n[用户情绪状态]\n" + affect_ctx

    valence_ctx = get_valence_context()
    if valence_ctx:
        system_msg += "\n[情绪变化]\n" + valence_ctx

    salience_ctx = get_salience_context()
    if salience_ctx:
        system_msg += "\n" + salience_ctx

    # ── 危机上下文注入 (仅当检测到危机时) ──────────────────
    if crisis_result:
        sev = crisis_result.get("severity", 0)
        llm_verified = crisis_result.get("llm_verified", False)
        urgency = crisis_result.get("urgency", "moderate")
        if sev >= 1.5 or llm_verified:
            crisis_ctx = get_crisis_context(sev, urgency=urgency, llm_verified=llm_verified)
            if crisis_ctx:
                system_msg += "\n\n" + crisis_ctx

    # Life domain context (what the user cares about lately)
    try:
        from services.psych.life_domains import get_life_domain_context
        life_ctx = get_life_domain_context()
        if life_ctx:
            system_msg += "\n\n" + life_ctx
    except Exception:
        pass

    # Drive state context (inner motivational state)
    drive_ctx = get_drive_context()
    if drive_ctx:
        system_msg += "\n\n[内心驱动状态]\n" + drive_ctx

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

    # MentalProcesses state machine mode (with drive influence)
    from services.emotion.affect import get_affect
    drives = get_drive_values()
    mode = determine_mode(_is_deep_question(msg), get_affect(), drives=drives)
    system_msg += "\n\n[互动模式]\n" + get_mode_suffix(mode)

    # Curiosity hint — only in explore/chat modes (not comfort/deep/play)
    if mode in ("explore", "chat"):
        try:
            from services.psych.entry_point import get_curiosity_hint
            global _turn_count
            hint = get_curiosity_hint(_turn_count)
            if hint:
                system_msg += "\n\n" + hint
        except Exception:
            pass

    drift_correction = get_drift_correction()
    if drift_correction:
        system_msg += "\n\n" + drift_correction

    self_eval_correction = get_self_eval_correction()
    if self_eval_correction:
        system_msg += "\n\n" + self_eval_correction

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


def _call_llm(messages: list, creativity: str = "normal",
              modules_config: dict | None = None,
              batch_mode: bool = False) -> tuple:
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

    # Batch mode: inject instructions before the JSON format reminder
    if batch_mode:
        msgs[-1]["content"] += (
            "\n\n用户一次发送了多个独立的问题/请求。"
            "请用scenes字段分批次逐一回答，每次只回答一个问题，简洁完整。"
            "reply字段放第一个问题的回答，scenes数组按顺序放后续每个问题的回答。"
            "每个回答独立成段，不要合并问题。"
        )

    msgs[-1]["content"] += "\n（请以上述JSON格式回复）"

    try:
        from services.emotion.affect import get_affect
        affect = get_affect()
        rhythm_temp = get_rhythm_temperature(affect)
        # Extract user message (last in the list) for mode detection
        user_msg = msgs[-1]["content"].split("\n（请以上述JSON格式回复）")[0] if msgs else ""
        drives = get_drive_values()
        mode = determine_mode(_is_deep_question(user_msg), affect, drives=drives)

        # Compute idle minutes for arousal state
        last_row = q("SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) AS secs FROM chat_history ORDER BY id DESC LIMIT 1", fetch="one")
        idle_min = (float(last_row["secs"]) / 60.0) if last_row and last_row["secs"] else 0

        arousal = determine_arousal(mode, affect, idle_min)
        temp = (rhythm_temp + get_mode_temp_mod(mode)
                + get_arousal_temp_mod(arousal)
                + get_drive_temp_mod(drives))
        is_story = (creativity == "high") or (modules_config or {}).get("scenes") in ("full", "compact")
        if is_story:
            temp += 0.05  # boost creativity for storytelling
        max_tok = 8192 if is_story else 4096
        resp = client.chat.completions.create(
            model=get_llm_model(), messages=msgs,
            temperature=temp, max_tokens=max_tok,
            timeout=90.0,
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


_SKY_EFFECT_PATTERNS = [
    '雨', '雪', '花瓣', '落叶', '花', '鲜花', '星星', '羽毛',
    '气泡', '音符', '光点', '蒲公英', '闪光', '雪花', '樱花',
    '叶子', '蝴蝶', '萤火虫', '流星', '星辰', '冰雹',
]


def _is_sky_effect(keywords: list[str]) -> bool:
    """Check if any keyword matches a sky/weather/漫天 pattern."""
    for kw in keywords:
        for pat in _SKY_EFFECT_PATTERNS:
            if pat in kw:
                return True
    return False


def _grid_has_pixels(grid) -> bool:
    """Check that a sprite grid has at least one non-zero (visible) pixel."""
    if not grid:
        return False
    for row in grid:
        s = str(row) if not isinstance(row, str) else row
        if any(ch != '0' for ch in s):
            return True
    return False


def _generate_sprites(keywords: list) -> list:
    """Generate pixel sprites from keywords.

    Checks the pre-built sprite library first. Falls back to LLM generation
    only for keywords not in the library. Runs synchronously (called via
    asyncio.to_thread).
    """
    if not keywords:
        return []

    # 1) Check pre-built sprite library
    lib_sprite = lookup_sprite(keywords)
    if lib_sprite:
        logger.info("_generate_sprites: library match for %s → %s", keywords, lib_sprite.get("name"))
        return [lib_sprite]

    # 2) Fall back to LLM generation
    client = get_llm()
    if client is None:
        return []
    user_prompt = build_sprite_user_prompt(keywords)
    if _is_sky_effect(keywords):
        user_prompt += (
            "\n[重要] 这是漫天效果！count必须20-30, spread>0.9, weight<0.3, duration>5。"
            "如果适合（下雨/暴晒），同时生成锚定物件（伞/帽子，anchor=\"head_top\",count=1,weight=0）。"
        )
    messages = [
        {"role": "system", "content": SPRITE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        resp = client.chat.completions.create(
            model=get_llm_model(), messages=messages,
            temperature=0.7, max_tokens=16384,
            timeout=20.0,
        )
        raw = resp.choices[0].message.content
        # Log without newlines so we can see the full response
        raw_flat = raw.replace('\n', '\\n') if raw else ''
        logger.info("_generate_sprites: raw=%s", raw_flat[:800] if raw_flat else '')
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            sprites = json.loads(raw[start:end])
            if isinstance(sprites, list):
                total_with_grid = sum(1 for s in sprites if isinstance(s, dict) and s.get("grid"))
                valid = [s for s in sprites if isinstance(s, dict) and s.get("grid") and _grid_has_pixels(s.get("grid"))]
                if total_with_grid > len(valid):
                    logger.warning("_generate_sprites: %d sprite(s) rejected for all-zero grid",
                                   total_with_grid - len(valid))
                logger.info("_generate_sprites: %d valid / %d total sprites for %s",
                            len(valid), len(sprites), keywords)
                for i, vs in enumerate(valid):
                    grid_type = type(vs.get("grid")).__name__
                    grid_len = len(vs.get("grid")) if vs.get("grid") else 0
                    logger.info("_generate_sprites: [%d] name=%s grid_type=%s grid_len=%s count=%s weight=%s anchor=%s",
                                i, vs.get("name", "?"), grid_type, grid_len,
                                vs.get("count"), vs.get("weight"), vs.get("anchor"))

                # Persist newly generated sprites for future reuse
                for vs in valid:
                    try:
                        name = vs.get("name", "")
                        if name and not lookup_sprite([name]):
                            persist_sprite(vs, [name] + keywords)
                    except Exception as e:
                        logger.warning("_generate_sprites: persist failed for %s: %s", vs.get("name"), e)

                return valid
        logger.warning("_generate_sprites: no valid JSON array in response (len=%d): %s", len(raw) if raw else 0, raw[:200])
        return []
    except Exception as e:
        logger.error("_generate_sprites failed: %s", e)
        return []


@router.post("/api/chat")
async def chat(req: ChatRequest):
    init_db()
    msg = req.message.strip()
    if not msg:
        return {"error": "empty message"}

    from services.emotion.salience import get_salience, init_salience_db
    from services.emotion.affect import get_affect

    is_deep = _is_deep_question(msg)
    pred_error = check_prediction(msg)
    if pred_error > 0.4:
        # Boost salience surprise for unexpected responses
        init_salience_db()
        s = get_salience()
        execute(
            "UPDATE salience_state SET value = %s WHERE dimension = 'surprise'",
            [round(min(1.0, s.get("surprise", 0.1) + pred_error * 0.3), 4)],
        )
    key = "exact:" + hashlib.md5(msg.encode()).hexdigest()[:16]

    # Dual-system gate: decide whether to engage System 2
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
            turn_id = new_row["id"] if new_row else None
            _post_reply_pipeline(msg, row["reply"], row["label"], turn_id=turn_id, is_deep=False)
            result = _row_to_response(row)
            for f in result.get("emotions", []):
                f.update(jitter_frame(f))
                f.update(scale_emotion_params(f))
            result["source"] = "cache"
            return result

    fg_token = llm_foreground()
    try:
        thinking = await asyncio.to_thread(_think, msg) if is_deep else None
        modules_config, _, creativity = await _analyze_intent(msg)
        batch_mode = modules_config.pop("__batch_mode", False) if modules_config else False

        # ── 治疗管线 ──────────────────────────────────────
        therapy_task = asyncio.create_task(analyze_therapy_intent(msg))
        crisis_result = crisis_keyword_check(msg)
        crisis_result["llm_verified"] = False
        crisis_result["urgency"] = "none"
        if crisis_result["trigger_llm_verify"]:
            try:
                verify = await asyncio.to_thread(crisis_llm_verify, msg)
                crisis_result["llm_verified"] = verify.get("crisis", False)
                crisis_result["llm_severity"] = verify.get("severity", 1)
                crisis_result["urgency"] = verify.get("urgency", "none")
            except Exception:
                logger.warning("危机LLM验证失败", exc_info=True)
        try:
            therapy_intent = await therapy_task
        except Exception:
            logger.warning("治疗意图分析失败", exc_info=True)
            therapy_intent = {"intent": "none", "confidence": 0.0}

        messages = _build_context(msg, thinking, modules_config=modules_config,
                                  crisis_result=crisis_result,
                                  therapy_intent=therapy_intent)
        data, fallback, llm_tags = await asyncio.to_thread(_call_llm, messages, creativity, modules_config, batch_mode)
    finally:
        llm_foreground_clear(fg_token)
    if fallback:
        return {"emotions": _fallback_emotion(), "reply": fallback, "source": "fallback"}

    emotions = data.get("emotions", [])
    if not isinstance(emotions, list) or not emotions:
        emotions = [make_default_frame()]
    parsed = [clamp_frame(f) for f in emotions]
    for f in parsed:
        f.update(jitter_frame(f))
        f.update(scale_emotion_params(f))
    reply_text = str(data.get("reply", "..."))
    scenes = data.get("scenes")
    if isinstance(scenes, list) and scenes:
        full_reply = reply_text + "\n\n" + "\n\n".join(
            str(s.get("reply", "")) for s in scenes if isinstance(s, dict) and s.get("reply")
        )
    else:
        full_reply = reply_text
        scenes = None
    result = {"emotions": parsed, "reply": reply_text, "color_fields": data.get("color_fields") or [], "sprite_keywords": data.get("sprite_keywords") or [], "background": data.get("background"), "whiteboard": data.get("whiteboard") or []}
    if scenes:
        result["scenes"] = scenes

    new_row = q(
        "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
        [msg, full_reply, parsed[0]["label"]], fetch="one",
    )
    turn_id = new_row["id"] if new_row else None
    _post_reply_pipeline(msg, result["reply"], parsed[0]["label"],
                         thinking=thinking, llm_tags=llm_tags, turn_id=turn_id,
                         is_deep=is_deep, crisis_result=crisis_result)

    first = parsed[0]
    seq = json.dumps(parsed) if len(parsed) > 1 else None
    _upsert(key, first, result["reply"], seq, result.get("color_fields"), result.get("background"), result.get("whiteboard"))
    _upsert(first["label"], first, result["reply"], seq, result.get("color_fields"), result.get("background"), result.get("whiteboard"))

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
                turn_id = new_row["id"] if new_row else None
                _post_reply_pipeline(msg, row["reply"], row["label"], turn_id=turn_id, is_deep=False)
                r = _row_to_response(row)
                for f in r.get("emotions", []):
                    f.update(jitter_frame(f))
                    f.update(scale_emotion_params(f))
                yield f"data: {json.dumps({'type': 'emotions', 'emotions': r['emotions'], 'label': row['label'], 'affect': _get_affect_dict(), 'color_fields': r.get('color_fields') or [], 'background': r.get('background'), 'whiteboard': r.get('whiteboard') or []}, ensure_ascii=False)}\n\n"
                reply = row["reply"]
                from services.cognition.state_machine import get_typing_delay
                from services.emotion.affect import get_affect as _get_affect_fn
                _cache_drives = get_drive_values()
                _cache_delay = get_typing_delay(
                    determine_mode(False, _get_affect_fn(), drives=_cache_drives),
                    _cache_drives, len(reply))
                for i in range(0, len(reply), 2):
                    yield f"data: {json.dumps({'type': 'text', 'text': reply[i:i+2]}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(_cache_delay)
                yield f"data: {json.dumps({'type': 'done', 'source': 'cache'}, ensure_ascii=False)}\n\n"
                return

        fg_token = llm_foreground()
        try:
            if is_deep:
                yield f"data: {json.dumps({'type': 'thinking'}, ensure_ascii=False)}\n\n"
                thinking = await asyncio.to_thread(_think, msg)
            else:
                thinking = None

            modules_config, _, creativity = await _analyze_intent(msg)
            batch_mode = modules_config.pop("__batch_mode", False) if modules_config else False

            # ── 治疗管线: 并行意图分析 + 危机检测 ────────────
            therapy_task = asyncio.create_task(analyze_therapy_intent(msg))
            # 第一层: 关键词危机检测 (同步, 零 LLM)
            crisis_result = crisis_keyword_check(msg)
            crisis_result["llm_verified"] = False
            crisis_result["urgency"] = "none"
            # 第二层: LLM 复核 (仅在触发时)
            if crisis_result["trigger_llm_verify"]:
                try:
                    verify = await asyncio.to_thread(crisis_llm_verify, msg)
                    crisis_result["llm_verified"] = verify.get("crisis", False)
                    crisis_result["llm_severity"] = verify.get("severity", 1)
                    crisis_result["urgency"] = verify.get("urgency", "none")
                except Exception:
                    logger.warning("危机LLM验证失败(stream)", exc_info=True)
            # 等待治疗意图分析完成
            try:
                therapy_intent = await therapy_task
            except Exception:
                logger.warning("治疗意图分析失败(stream)", exc_info=True)
                therapy_intent = {"intent": "none", "confidence": 0.0}

            messages = _build_context(msg, thinking, modules_config=modules_config,
                                      crisis_result=crisis_result,
                                      therapy_intent=therapy_intent)
            data, fallback, llm_tags = await asyncio.to_thread(_call_llm, messages, creativity, modules_config, batch_mode)
        finally:
            llm_foreground_clear(fg_token)
        if fallback:
            yield f"data: {json.dumps({'type': 'emotions', 'emotions': _fallback_emotion(), 'label': 'sheepish', 'affect': _get_affect_dict(), 'color_fields': []}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'text': fallback}, ensure_ascii=False)}\n\n"
            return

        emotions = data.get("emotions", [])
        if not isinstance(emotions, list) or not emotions:
            emotions = [make_default_frame()]
        parsed = [clamp_frame(f) for f in emotions]
        for f in parsed:
            f.update(jitter_frame(f))
            f.update(scale_emotion_params(f))
        reply = str(data.get("reply", "..."))
        scenes = data.get("scenes")
        if isinstance(scenes, list) and scenes:
            full_reply = reply + "\n\n" + "\n\n".join(
                str(s.get("reply", "")) for s in scenes if isinstance(s, dict) and s.get("reply")
            )
        else:
            full_reply = reply
            scenes = None  # ensure None for non-list / empty list

        # Persist before streaming — prevents data loss on client disconnect
        new_row = q(
            "INSERT INTO chat_history (user_msg, avatar_reply, emotion_label) VALUES (%s, %s, %s) RETURNING id",
            [msg, full_reply, parsed[0]["label"]], fetch="one",
        )
        turn_id = new_row["id"] if new_row else None
        _post_reply_pipeline(msg, reply, parsed[0]["label"],
                             thinking=thinking, llm_tags=llm_tags, turn_id=turn_id,
                             is_deep=is_deep, crisis_result=crisis_result)

        first = parsed[0]
        seq = json.dumps(parsed) if len(parsed) > 1 else None
        _upsert(key, first, reply, seq, data.get("color_fields"), data.get("background"), data.get("whiteboard"))
        _upsert(first["label"], first, reply, seq, data.get("color_fields"), data.get("background"), data.get("whiteboard"))

        lbl = parsed[0]["label"] if parsed else "neutral"
        cf = data.get("color_fields") or []
        bg = data.get("background")
        wb = data.get("whiteboard") or []
        yield f"data: {json.dumps({'type': 'emotions', 'emotions': parsed, 'label': lbl, 'affect': _get_affect_dict(), 'color_fields': cf, 'background': bg, 'whiteboard': wb}, ensure_ascii=False)}\n\n"
        # Scene 0 start event (protocol consistency with scene 1..N)
        if scenes:
            yield f"data: {json.dumps({'type': 'scene_start', 'index': 0, 'total': len(scenes) + 1, 'emotions': parsed, 'label': lbl, 'affect': _get_affect_dict(), 'color_fields': cf, 'background': bg, 'whiteboard': wb, 'batch_mode': batch_mode}, ensure_ascii=False)}\n\n"

        # Start background sprite generation if keywords present
        raw_keywords = data.get("sprite_keywords") or []
        # Handle both string and list formats from LLM
        if isinstance(raw_keywords, str):
            sprite_keywords = [raw_keywords]
        elif isinstance(raw_keywords, list):
            sprite_keywords = [k for k in raw_keywords if isinstance(k, str)]
        else:
            sprite_keywords = []
        if sprite_keywords:
            logger.info("Sprite keywords: %s", sprite_keywords)
        sprite_task = None
        if sprite_keywords:
            fg_token2 = llm_foreground()
            try:
                sprite_task = asyncio.create_task(
                    asyncio.to_thread(_generate_sprites, sprite_keywords)
                )
            finally:
                llm_foreground_clear(fg_token2)

        sprites_sent = False
        try:
            # Compute dynamic typing delay for this reply
            from services.cognition.state_machine import get_typing_delay
            from services.emotion.affect import get_affect as _get_affect_fn
            _stream_drives = get_drive_values()
            _stream_affect = _get_affect_fn()
            _stream_mode = determine_mode(is_deep, _stream_affect, drives=_stream_drives)
            _stream_delay = get_typing_delay(_stream_mode, _stream_drives, len(reply))
            for i in range(0, len(reply), 2):
                yield f"data: {json.dumps({'type': 'text', 'text': reply[i:i+2]}, ensure_ascii=False)}\n\n"
                # Check if sprites finished during text streaming
                if sprite_task and not sprites_sent and sprite_task.done():
                    try:
                        sprites = sprite_task.result()
                        if sprites:
                            logger.info("Sending %d sprites during text streaming", len(sprites))
                            yield f"data: {json.dumps({'type': 'pixel_sprites', 'sprites': sprites}, ensure_ascii=False)}\n\n"
                        sprites_sent = True
                    except Exception as e:
                        logger.error("Sprite task failed (during stream): %s", e)
                        sprites_sent = True
                await asyncio.sleep(_stream_delay)

            # If sprites not ready yet, wait with timeout (8s max)
            if sprite_task and not sprites_sent:
                try:
                    sprites = await asyncio.wait_for(sprite_task, timeout=8.0)
                    if sprites:
                        logger.info("Sending %d sprites after text streaming", len(sprites))
                        yield f"data: {json.dumps({'type': 'pixel_sprites', 'sprites': sprites}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    logger.warning("Sprite generation timed out after 8s, skipping sprites")
                except Exception as e:
                    logger.error("Sprite task failed (after stream): %s", e)

            # Scene iteration: if LLM returned multiple story scenes, stream them
            if scenes:
                scene_total = len(scenes) + 1  # +1 for the initial scene 0
                for si, scene in enumerate(scenes):
                    if not isinstance(scene, dict):
                        continue
                    scene_idx = si + 1
                    scene_reply = scene.get("reply") or ""
                    if not scene_reply:
                        continue

                    # Signal end of previous scene
                    yield f"data: {json.dumps({'type': 'scene_done', 'index': scene_idx - 1, 'total': scene_total, 'batch_mode': batch_mode}, ensure_ascii=False)}\n\n"

                    # Build scene_start with visual params
                    se = scene.get("emotions")
                    if isinstance(se, list) and se:
                        scene_emotions = [clamp_frame(f) for f in se]
                        for f in scene_emotions:
                            f.update(jitter_frame(f))
                            f.update(scale_emotion_params(f))
                        scene_label = scene_emotions[0].get("label", lbl)
                    else:
                        scene_emotions = parsed  # inherit from scene 0
                        scene_label = lbl

                    scene_cf = scene.get("color_fields") or cf
                    scene_bg = scene.get("background") or bg
                    scene_wb = scene.get("whiteboard") or wb

                    yield f"data: {json.dumps({'type': 'scene_start', 'index': scene_idx, 'total': scene_total, 'emotions': scene_emotions, 'label': scene_label, 'affect': _get_affect_dict(), 'color_fields': scene_cf, 'background': scene_bg, 'whiteboard': scene_wb, 'batch_mode': batch_mode}, ensure_ascii=False)}\n\n"

                    # Stream scene text
                    _scene_delay = get_typing_delay(_stream_mode, _stream_drives, len(scene_reply))
                    for i in range(0, len(scene_reply), 2):
                        yield f"data: {json.dumps({'type': 'text', 'text': scene_reply[i:i+2]}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(_scene_delay)

                # Signal end of final scene
                yield f"data: {json.dumps({'type': 'scene_done', 'index': scene_total - 1, 'total': scene_total, 'batch_mode': batch_mode}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'source': 'llm', 'batch_mode': batch_mode}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Streaming interrupted: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'text': '嗯...说到一半信号断了，再说一次？✨'}, ensure_ascii=False)}\n\n"

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
