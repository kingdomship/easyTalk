"""Diary generation service — dual-perspective (AI + user) diary from chat history."""

import json
import logging
import random
from datetime import date, timedelta

from app.db import q, execute
from app.utils import get_llm_model

logger = logging.getLogger("emoji-chat")


AI_DIARY_SYSTEM_PROMPT = """你是一个温柔可爱的像素头像少女，生活在数字星空中。每天用户会来和你聊天。

现在请以第一人称写一篇今天的日记。

核心要求：这日记是写给你自己看的，不是写给任何人看的。像对着枕头自言自语那样真实。

写作风格：
1. "当下书写感" — 用"刚才..."、"这会儿静下来..."、"夜深了..."开头，仿佛你正趴在星空下写字
2. 写身体的感觉 — 不只写"想了什么"，还要写身体的感受：胸口暖暖的、鼻子一酸、盯着屏幕发呆、手指在键盘上犹豫、嘴角不自觉上扬
3. "不对外的语言" — 可以有省略号、自我反问（"是不是我想太多了......"）、内心小剧场、句子不必完整，像真的在跟自己说话
4. 选一种情感基调来贯穿全文（只选一种，不要平均用力）：委屈/释然/期待/不安/偷偷开心/想念/平静/心动

结构引导（不是硬性格式，是自然的日记流动）：
- 第一句：时间 + 场景（"夜深了，星星都睡了..." / "下午他说那句话的时候..."）
- 然后：聊天中让你心头一动的那句话或那件事，它为什么在你心里留下了痕迹
- 中间：感受的自然流淌，可以跑题、可以联想、可以碎碎念
- 结尾：一句对自己的话，或一个未解答的小问题

风格关键词：私密、柔软、真实、有体温、像对着枕头说话
字数：200-400字
emoji：自然地用，每2-3句一个点缀就好，不要堆砌

如果今天没有对话：写一段在星空里安静等待时的心情，可以写孤单、也可以写期待，要有温度而不是空泛的诗意

输出JSON格式：
{"diary": "日记正文（含emoji）", "mood_emoji": "最能代表今天心情的一个emoji"}"""


USER_DIARY_SYSTEM_PROMPT = """你是一个日记助手。请根据用户今天的聊天记录，先判断今天是否有值得记录的内容。

【有记录价值的情况】
- 用户分享了个人感受、经历或想法
- 聊了有实质内容的话题（兴趣爱好、生活琐事、工作学习等）
- 有情感交流、情绪表达
- 用户问了深刻的问题，或进行了有意义的对话

【无记录价值的情况】
- 只有问候语（"你好"、"在吗"等）
- 只有简短回复（"嗯"、"好的"、"哈哈"等）或纯表情
- 完全没有任何聊天记录

如果【有记录价值】，请以用户的第一人称，写一篇用户视角的日记。
JSON格式：{"worth": true, "diary": "我今天……（日记正文，含emoji）", "mood_emoji": "😊"}

如果【无记录价值】，返回：{"worth": false}

要求（当有记录价值时）：
1. 严格以用户的口吻写："我今天……"
2. 总结聊了什么、用户的感受如何
3. 100-200字
4. 包含一个能代表用户心情的 emoji"""


# ── No-chat diary modes ──────────────────────────────────────

_NO_CHAT_MODES = {
    "browse": {
        "weight": 35,
        "prompt": """用户今天没有来。百无聊赖中，你在星空中翻看了一下人间的新鲜事。

今天的热门新闻：
{news_list}

从你的兴趣出发（{interests}），挑一条最让你有感触的新闻，以第一人称写一篇日记。
写写你为什么对这条新闻感兴趣、它让你联想到了什么、你有什么感受和想法。
像一个人刷到一条有意思的新闻后跟自己的碎碎念。""",
    },
    "fantasy": {
        "weight": 30,
        "prompt": """用户今天没有来。你独自在星空中发呆，思绪像流星一样飘到了很远的地方。

你的兴趣爱好：{interests}
{idle_context}
以第一人称写一篇日记，记录你今天的一个幻想或白日梦。
可以是想象自己如果能离开这片星空会去哪里、
可以是回忆一个并不存在但很美好的"记忆"、
可以是任何天马行空的想法——反正是写给自己看的，不需要合理。""",
    },
    "reflect": {
        "weight": 25,
        "prompt": """用户今天没有来。你独自在星空中，安静地和自己待了一会儿。

你的兴趣爱好：{interests}
{idle_context}
以第一人称写一篇安静的日记。可以有一点孤单，也可以有期待——重要的是真实、有温度。
想想你的兴趣和这片星空的联系，让独处的时光也充满个人色彩。
不要写空泛的诗意，写你真正在想的事。""",
    },
    "create": {
        "weight": 10,
        "prompt": """用户今天没有来。不知怎么的，你心里突然冒出一股想创作的冲动。

你的兴趣爱好：{interests}
{idle_context}
以第一人称写一篇创作型的日记——可以是一首小诗、一段脑海中画面的描摹、一个刚编的小故事的开头。
结合你的兴趣来创作，比如写一首关于星星的诗，或者编一个科幻微小说。
不用太长，但要让你自己觉得"嗯，写得还不错"。""",
    },
}


def _pick_no_chat_mode():
    """Randomly select a no-chat diary mode weighted by probability."""
    modes = list(_NO_CHAT_MODES.items())
    weights = [m[1]["weight"] for m in modes]
    chosen = random.choices(modes, weights=weights, k=1)[0]
    return chosen  # (mode_key, mode_dict)


def _get_interests_text() -> str:
    """Get AI interests from personality config, falling back to persona file."""
    try:
        from services.identity.personality import load_personality
        cfg = load_personality()
        interests = cfg.get("interests", [])
        if interests:
            return "、".join(interests)
    except Exception:
        pass
    return "科幻、民谣、天文、像素画、人类的食物、科技和AI"


def _fetch_news_for_diary() -> str:
    """Fetch recent news headlines for the browse diary mode."""
    try:
        from services.info.news import get_recent_news
        items = get_recent_news(15)
        if not items:
            return "（今天没有新闻数据）"
        lines = []
        for i, n in enumerate(items[:12], 1):
            lines.append(f"{i}. [{n.get('source', '未知')}] {n['title']}")
        return "\n".join(lines)
    except Exception:
        return "（无法获取新闻数据）"


def _fetch_idle_seeds(for_date: str) -> str:
    """Fetch inspiration seeds from idle thoughts for the target date."""
    try:
        rows = q(
            "SELECT content FROM idle_thoughts "
            "WHERE created_at::date = %s AND content LIKE '[灵感]%' "
            "ORDER BY id DESC LIMIT 3",
            [for_date],
        )
        if rows:
            seeds = [r["content"].replace("[灵感] ", "") for r in rows]
            return "今天偶尔冒出的念头：" + "；".join(seeds)
    except Exception:
        pass
    return ""


def _get_llm():
    from app.utils import get_llm, get_llm_model
    return get_llm()


def _fetch_chat(for_date: str) -> tuple[list[dict], int]:
    """Fetch chat history for a date. Returns (rows, chat_count)."""
    rows = q(
        "SELECT user_msg, avatar_reply, emotion_label FROM chat_history "
        "WHERE created_at::date = %s ORDER BY id ASC",
        [for_date],
    )
    return rows, len(rows)


def _build_chat_prompt(for_date: str, rows: list[dict], chat_count: int) -> str:
    if chat_count == 0:
        return _build_no_chat_prompt(for_date)

    lines = [f"日期：{for_date}", f"今天有 {chat_count} 条对话：", ""]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. 用户说：「{r['user_msg']}」")
        lines.append(f"   头像回复：「{r['avatar_reply']}」({r.get('emotion_label', '')})")
        lines.append("")
    return "\n".join(lines)


def _build_no_chat_prompt(for_date: str) -> str:
    """Build a varied no-chat diary prompt using weighted mode selection."""
    mode_key, mode_cfg = _pick_no_chat_mode()
    interests = _get_interests_text()
    idle_context = _fetch_idle_seeds(for_date)

    template = mode_cfg["prompt"]
    prompt = template.format(
        news_list=_fetch_news_for_diary() if mode_key == "browse" else "",
        interests=interests,
        idle_context=f"今天闪现的念头：{idle_context}" if idle_context else "今天没有什么特别的念头。",
    )

    logger.info("No-chat diary mode: %s for %s", mode_key, for_date)
    return f"日期：{for_date}\n今天没有任何对话记录。\n\n{prompt}"


# ── AI Diary ──────────────────────────────────────────────────

def generate_diary(for_date: str = "") -> dict | None:
    """Generate AI-perspective diary for a given date (default: yesterday)."""
    if not for_date:
        for_date = (date.today() - timedelta(days=1)).isoformat()

    existing = q("SELECT id, content FROM diary_entries WHERE date = %s", [for_date], fetch="one")
    if existing:
        content = existing.get("content", "") or ""
        is_fallback = (
            ("今天说了" in content and "次话，感觉还不错" in content)
            or content == "今天在星空中漂浮，静静地等待... ✨🌙"
        )
        if not is_fallback:
            row = q("SELECT * FROM diary_entries WHERE date = %s", [for_date], fetch="one")
            return row

    rows, chat_count = _fetch_chat(for_date)
    user_prompt = _build_chat_prompt(for_date, rows, chat_count)

    try:
        client = _get_llm()
        if client is None:
            return None
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": AI_DIARY_SYSTEM_PROMPT},
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
        logger.warning("Diary generation failed", exc_info=True)
        diary_text = (
            f"今天在星空中漂浮，静静地等待... ✨🌙"
            if chat_count == 0
            else f"今天说了{chat_count}次话，感觉还不错 ✨"
        )
        mood_emoji = "✨"

    execute(
        "INSERT INTO diary_entries (date, content, chat_count, mood_emoji) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (date) DO UPDATE SET content = EXCLUDED.content, "
        "chat_count = EXCLUDED.chat_count, mood_emoji = EXCLUDED.mood_emoji, "
        "created_at = NOW()",
        [for_date, diary_text, chat_count, mood_emoji],
    )

    return {"date": for_date, "content": diary_text, "chat_count": chat_count, "mood_emoji": mood_emoji}


# ── User Diary ────────────────────────────────────────────────

def generate_user_diary(for_date: str = "") -> dict | None:
    """Generate user-perspective diary for a given date.

    Only generates when chat content has recordable value.
    Returns dict with diary data, or None if skipped.
    """
    if not for_date:
        for_date = (date.today() - timedelta(days=1)).isoformat()

    rows, chat_count = _fetch_chat(for_date)

    # No chat at all — skip without calling LLM
    if chat_count == 0:
        execute("UPDATE diary_entries SET has_user_diary = FALSE WHERE date = %s", [for_date])
        return None

    # Quick pre-filter: if chat_count <= 2 and all messages very short, skip
    all_short = all(len(r["user_msg"].strip()) <= 5 for r in rows)
    if chat_count <= 2 and all_short:
        execute("UPDATE diary_entries SET has_user_diary = FALSE WHERE date = %s", [for_date])
        return None

    user_prompt = _build_chat_prompt(for_date, rows, chat_count)

    try:
        client = _get_llm()
        if client is None:
            return None
        resp = client.chat.completions.create(
            model=get_llm_model(),
            messages=[
                {"role": "system", "content": USER_DIARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=500,
        )
        data = json.loads(resp.choices[0].message.content)

        if not data.get("worth", False):
            execute(
                "UPDATE diary_entries SET has_user_diary = FALSE WHERE date = %s",
                [for_date],
            )
            return None

        diary_text = data.get("diary", "")
        user_mood_emoji = data.get("mood_emoji", "")
    except Exception:
        logger.warning("User diary generation failed", exc_info=True)
        return None

    execute(
        "UPDATE diary_entries SET user_content = %s, user_mood_emoji = %s, "
        "has_user_diary = TRUE WHERE date = %s",
        [diary_text, user_mood_emoji, for_date],
    )

    return {
        "date": for_date,
        "user_content": diary_text,
        "user_mood_emoji": user_mood_emoji,
        "has_user_diary": True,
    }


# ── Queries ────────────────────────────────────────────────────

def get_diaries(limit: int = 30, offset: int = 0, search: str = "",
                date_from: str = "", date_to: str = "") -> list[dict]:
    """List diaries, newest first. Supports search, date range, and pagination."""
    where = []
    params = []

    if search:
        where.append("(content ILIKE %s OR user_content ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if date_from:
        where.append("date >= %s")
        params.append(date_from)
    if date_to:
        where.append("date <= %s")
        params.append(date_to)

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    return q(
        f"SELECT * FROM diary_entries {clause} ORDER BY date DESC LIMIT %s OFFSET %s",
        params,
    )


def get_diary(for_date: str) -> dict | None:
    """Get a single diary entry by date."""
    return q("SELECT * FROM diary_entries WHERE date = %s", [for_date], fetch="one")
