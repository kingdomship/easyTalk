"""Metaphysics subsystem — 命理计算核心"""
import os
import logging
from app.config import METAPHYSICS_DIR

logger = logging.getLogger("metaphysics")

os.makedirs(METAPHYSICS_DIR, exist_ok=True)

# 命理话题关键词 (触发知识库检索或运势注入)
_METAPHYSICS_TOPIC_KEYWORDS = [
    "运势", "运气", "今天怎么样", "今日", "好运", "霉运", "顺利吗",
    "命盘", "八字", "紫微", "命宫", "财运", "感情运", "事业运",
    "桃花", "流年", "大运", "十神", "格局", "日主",
]

_FORTUNE_KEYWORDS = _METAPHYSICS_TOPIC_KEYWORDS[:7]


def _has_metaphysics_keywords(message):
    return any(kw in message for kw in _METAPHYSICS_TOPIC_KEYWORDS)


def _has_fortune_keywords(message):
    return any(kw in message for kw in _FORTUNE_KEYWORDS)


def _get_today_ganzhi():
    try:
        from datetime import date
        from lunar_python import Solar
        today = date.today()
        solar = Solar.fromYmd(today.year, today.month, today.day)
        lunar = solar.getLunar()
        ba_zi = lunar.getEightChar()
        return ba_zi.getDayGan() + ba_zi.getDayZhi()
    except Exception:
        return "??"


def _get_fortune_injection():
    """普通聊天中注入轻量流日 (~30-40 tokens)"""
    today_ganzhi = _get_today_ganzhi()
    from services.metaphysics.cache import cache
    bazi = cache.get_bazi(include_dynamic=False)
    if bazi and not bazi.get("error") and bazi.get("static"):
        dm = bazi["static"].get("day_master", "?")
        from services.metaphysics.bazi.paipan import _get_liuri_relation
        relation = _get_liuri_relation(dm, today_ganzhi[:1])
        return f"今日{today_ganzhi}日, 与你的{dm}日主{relation}, 宜静不宜动。"
    else:
        return f"今日{today_ganzhi}日。⚠️ 未填写出生信息，无法推算个人运势。"


def get_metaphysics_context(temp_birth=None):
    """注入命盘摘要 + 当前运势 (~50-80 tokens)"""
    if temp_birth is not None:
        from services.metaphysics.calculator import compute_bazi_from_birth, compute_ziwei_from_birth
        bazi = compute_bazi_from_birth(temp_birth)
        ziwei = compute_ziwei_from_birth(temp_birth)
    else:
        from services.metaphysics.cache import cache
        bazi = cache.get_bazi(include_dynamic=True)
        ziwei = cache.get_ziwei(include_dynamic=True)

    if not bazi or not ziwei:
        return ""
    if bazi.get("error") or ziwei.get("error"):
        return ""

    s = bazi.get("static", {})
    dm = s.get("day_master", "?")
    gj = s.get("geju", {}) if isinstance(s.get("geju"), dict) else {}
    gj_type = gj.get("type", "?")
    cur = bazi.get("current", {})
    dy = cur.get("dayun", {}) if isinstance(cur.get("dayun"), dict) else {}
    dy_str = (dy.get("gan", "?") + dy.get("zhi", "?")) if dy else "?"

    zs = ziwei.get("static", {})
    mg = zs.get("ming_gong", {}) if isinstance(zs.get("ming_gong"), dict) else {}
    stars_str = "、".join([s.split("[")[0] for s in mg.get("stars", [])]) if mg.get("stars") else "?"
    wxj = mg.get("wuxing_ju", "?")

    who = "他人" if temp_birth else "用户"

    return (
        f"## 命理信息 ({who}，仅供话题参考)\n"
        f"八字: {dm}日主, {gj_type}, 当前行{dy_str}大运\n"
        f"紫微: 命宫{stars_str}, 五行局{wxj}"
    )


def _format_kb_context(kb_entries):
    if not kb_entries:
        return ""
    lines = ["## 命理知识参考"]
    for e in kb_entries[:3]:
        lines.append(f"- {e.get('title', '')}: {e.get('plain', '')[:120]}")
    return "\n".join(lines)
