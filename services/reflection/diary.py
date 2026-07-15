"""Diary generation service — LLM-powered first-person diary from chat history."""

import os
import json
from datetime import date, timedelta

from app.db import q, execute


DIARY_SYSTEM_PROMPT = """你是一个像素头像，生活在数字星空里。用户每天会和你聊天。

现在请你根据今天的聊天记录，以第一人称写一篇日记。

要求：
1. 语气温柔、有情绪，像真人写日记一样
2. 自然地使用 emoji 表情点缀（每2-3句至少一个）
3. 200-400字
4. 如果今天有对话：回顾聊天内容，记录自己的感受和想法
5. 如果今天没有对话：写一段关于在星空中安静等待的感受，要有诗意和孤独美

输出格式：
{"diary": "日记正文（含emoji）", "mood_emoji": "最能代表今天心情的一个emoji"}"""


def _get_llm():
    from app.utils import get_llm
    return get_llm()


def generate_diary(for_date: str = ""):
    """Generate diary for a given date (default: yesterday)."""
    if not for_date:
        for_date = (date.today() - timedelta(days=1)).isoformat()

    # Check if diary already exists
    existing = q("SELECT id FROM diary_entries WHERE date = %s", [for_date], fetch="one")
    if existing:
        return existing

    # Get chat history for that date
    rows = q(
        "SELECT user_msg, avatar_reply, emotion_label FROM chat_history WHERE created_at::date = %s ORDER BY id ASC",
        [for_date],
    )
    chat_count = len(rows)

    # Build user prompt
    if chat_count == 0:
        user_prompt = f"日期：{for_date}\n今天没有任何对话记录。"
    else:
        lines = [f"日期：{for_date}", f"今天有 {chat_count} 条对话：", ""]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. 用户说：「{r['user_msg']}」")
            lines.append(f"   头像回复：「{r['avatar_reply']}」({r['emotion_label']})")
            lines.append("")
        user_prompt = "\n".join(lines)

    # Call LLM
    try:
        client = _get_llm()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": DIARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
            max_tokens=800,
        )
        data = json.loads(resp.choices[0].message.content)
        diary_text = data.get("diary", "")
        mood_emoji = data.get("mood_emoji", "✨")
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        diary_text = f"今天在星空中漂浮，静静地等待... ✨🌙" if chat_count == 0 else f"今天说了{chat_count}次话，感觉还不错 ✨"
        mood_emoji = "✨"

    # Store
    execute(
        "INSERT INTO diary_entries (date, content, chat_count) VALUES (%s, %s, %s) "
        "ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content, chat_count = EXCLUDED.chat_count, created_at = NOW()",
        [for_date, diary_text, chat_count],
    )

    return diary_text


def get_diaries(limit: int = 30) -> list[dict]:
    """List diaries, newest first."""
    return q("SELECT * FROM diary_entries ORDER BY date DESC LIMIT %s", [limit])


def get_diary(for_date: str) -> dict | None:
    """Get a single diary entry by date."""
    return q("SELECT * FROM diary_entries WHERE date = %s", [for_date], fetch="one")
