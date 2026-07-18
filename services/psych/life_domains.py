"""Life domain tracking — structured awareness of what the user cares about.

Tracks 6 life domains with status (positive/negative/neutral) and salience.
Uses a hybrid approach: keyword-based domain detection + Panksepp affect scores
for status inference. Zero extra LLM calls — reuses existing affect data.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone

from app.config import LIFE_DOMAINS_PATH, archive_lock

logger = logging.getLogger("emoji-chat")

# ── Domain definitions ─────────────────────────────────────────────────────

DOMAINS = {
    "work": {
        "label": "工作",
        "keywords": [
            "工作", "上班", "加班", "老板", "领导", "同事", "职场", "项目",
            "开会", "汇报", "跳槽", "面试", "辞职", "裁员", "薪资", "工资",
            "任务", "ddl", "deadline", "甲方", "乙方", "客户", "出差",
        ]
    },
    "relationships": {
        "label": "关系",
        "keywords": [
            "朋友", "对象", "女朋友", "男朋友", "恋人", "伴侣", "家人", "父母",
            "妈妈", "爸爸", "孩子", "老公", "老婆", "闺蜜", "兄弟", "分手",
            "吵架", "冷战", "相亲", "约会", "暧昧", "表白", "暗恋", "前任",
        ]
    },
    "health": {
        "label": "健康",
        "keywords": [
            "身体", "健康", "生病", "医院", "失眠", "焦虑", "抑郁", "运动",
            "健身", "跑步", "瑜伽", "减肥", "饮食", "熬夜", "头疼", "累",
            "疲劳", "体检", "心理", "emo", "压力", "崩溃",
        ]
    },
    "hobbies": {
        "label": "兴趣",
        "keywords": [
            "喜欢", "爱好", "游戏", "电影", "音乐", "书", "摄影", "画画",
            "旅行", "旅游", "美食", "做菜", "猫", "狗", "宠物", "动漫",
            "追剧", "综艺", "b站", "番", "小说", "写作", "编程", "代码",
        ]
    },
    "finance": {
        "label": "财务",
        "keywords": [
            "钱", "工资", "理财", "买房", "租房", "贷款", "花销", "省钱",
            "投资", "股票", "基金", "副业", "赚钱", "贵", "便宜", "消费",
        ]
    },
    "growth": {
        "label": "成长",
        "keywords": [
            "学习", "考试", "考证", "考研", "读书", "技能", "进步", "改变",
            "方向", "迷茫", "意义", "目标", "计划", "未来", "梦想", "努力",
            "坚持", "自律", "拖延", "效率", "提升", "课程", "教程", "学",
        ]
    },
}

# Affect dimension → status mapping
# High SEEKING + PLAY → positive; high FEAR/PANIC/RAGE → negative
_POSITIVE_AFFECT = {"SEEKING", "PLAY", "CARE"}
_NEGATIVE_AFFECT = {"FEAR", "PANIC", "RAGE"}

_lock = threading.Lock()


# ── Persistence ─────────────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(LIFE_DOMAINS_PATH):
        try:
            with open(LIFE_DOMAINS_PATH) as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to load life domains", exc_info=True)
    return {
        key: {"status": "neutral", "salience": 0.0, "last_mention": ""}
        for key in DOMAINS
    }


def _save(data: dict):
    try:
        with open(LIFE_DOMAINS_PATH, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("Failed to save life domains", exc_info=True)


# ── Detection ───────────────────────────────────────────────────────────────

def detect_domain(msg: str) -> tuple[list[str], dict[str, float]]:
    """Return (matched_domains, {domain: keyword_count}) for a user message."""
    matched = []
    counts = {}
    for key, dom in DOMAINS.items():
        cnt = sum(1 for kw in dom["keywords"] if kw in msg)
        if cnt > 0:
            matched.append(key)
            counts[key] = cnt
    return matched, counts


def infer_status(msg: str, affect: dict | None = None) -> str:
    """Infer domain status from affect dimensions and sentiment cues.

    Uses existing Panksepp affect scores as the primary signal.
    Falls back to simple negation-word heuristics if affect is unavailable.
    """
    if affect:
        pos = sum(affect.get(dim.lower(), 0) for dim in _POSITIVE_AFFECT)
        neg = sum(affect.get(dim.lower(), 0) for dim in _NEGATIVE_AFFECT)
        if pos - neg > 0.1:
            return "positive"
        elif neg - pos > 0.1:
            return "negative"
        return "neutral"

    # Fallback: simple negation detection
    neg_words = ["烦", "累", "难", "讨厌", "无语", "崩溃", "压力", "焦虑", "不开心"]
    pos_words = ["开心", "喜欢", "期待", "有意思", "好玩", "棒", "不错", "哈哈"]
    neg_cnt = sum(1 for w in neg_words if w in msg)
    pos_cnt = sum(1 for w in pos_words if w in msg)
    if pos_cnt > neg_cnt:
        return "positive"
    elif neg_cnt > pos_cnt:
        return "negative"
    return "neutral"


# ── Update (called from _post_reply_pipeline) ───────────────────────────────

def update_life_domains(msg: str, affect: dict | None = None):
    """Update life domain state based on a single user message.

    Lightweight — keyword matching + affect inference, no LLM call.
    Designed to run every turn in the background pipeline.
    """
    matched, counts = detect_domain(msg)
    if not matched:
        return

    with _lock:
        data = _load()
        now = datetime.now(timezone.utc).isoformat()
        for domain in matched:
            entry = data.get(domain, {"status": "neutral", "salience": 0.0, "last_mention": ""})
            # EMA-smooth salience (alpha=0.1, stronger because keyword hits are already filtered)
            hit = min(counts[domain] / 3.0, 1.0)
            entry["salience"] = round(entry["salience"] * 0.9 + hit * 0.1, 3)
            # Infer status from affect (updates immediately, not smoothed)
            entry["status"] = infer_status(msg, affect)
            # Last mention snapshot
            entry["last_mention"] = msg[:200]
            data[domain] = entry
        _save(data)


# ── Context injection ───────────────────────────────────────────────────────

def get_life_domain_context() -> str:
    """Generate natural-language context string for system prompt injection.

    Returns empty string if no domains have salience > 0.05.
    Only includes domains the user has recently talked about.
    """
    data = _load()
    active = [
        (key, dom, data[key])
        for key, dom in DOMAINS.items()
        if data.get(key, {}).get("salience", 0) > 0.05
    ]
    if not active:
        return ""

    # Sort by salience, top 3 most salient
    active.sort(key=lambda x: x[2]["salience"], reverse=True)
    active = active[:3]

    lines = ["## 用户近况（仅供参考，不要每轮都提）"]
    for key, dom, entry in active:
        status_emoji = {"positive": "👍", "negative": "😔", "neutral": "💬"}.get(entry["status"], "")
        status_text = {"positive": "顺利", "negative": "有困扰", "neutral": "在关注"}.get(entry["status"], "")
        lines.append(f"- {dom['label']}：{status_text} {status_emoji}")

    # Guidance strength depends on how much info we have
    if len(active) <= 2:
        lines.append("（你目前对用户了解不多，上面这些偶尔提到就行，不要每轮都拿出来说。多聊新的，少翻旧账。）")
    else:
        lines.append("（你心里有数就好，挑相关的自然带过，不要逐条复述。）")
    return "\n".join(lines)
