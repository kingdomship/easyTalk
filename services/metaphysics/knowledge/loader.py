"""Knowledge base loader — ~270 entries, ~170KB, loaded at import time."""
import json
import os
import logging

logger = logging.getLogger("metaphysics")

_dir = os.path.dirname(__file__)

_KB_BAZI: list[dict] = []
_KB_ZIWEI: list[dict] = []
_ALL_TAGS: set[str] = set()


def _load_kb():
    global _KB_BAZI, _KB_ZIWEI, _ALL_TAGS
    try:
        with open(os.path.join(_dir, "bazi_kb.json"), "r") as f:
            _KB_BAZI = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("bazi_kb.json not found or invalid, using empty KB")
        _KB_BAZI = []
    try:
        with open(os.path.join(_dir, "ziwei_kb.json"), "r") as f:
            _KB_ZIWEI = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("ziwei_kb.json not found or invalid, using empty KB")
        _KB_ZIWEI = []
    for entry in _KB_BAZI + _KB_ZIWEI:
        _ALL_TAGS.update(entry.get("tags", []))


_load_kb()


def search_kb(tags, limit=5):
    scored = []
    for entry in _KB_BAZI + _KB_ZIWEI:
        score = sum(
            1 for t in tags
            if t in entry.get("tags", [])
            or t == entry.get("title", "")
            or t == entry.get("category", "")
        )
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:limit]]


_TAG_ALIASES = {
    "财运":   ["财帛宫", "正财", "偏财"],
    "事业运": ["官禄宫", "正官", "七杀"],
    "感情运": ["夫妻宫", "桃花", "红鸾"],
    "健康":   ["疾厄宫", "五行平衡"],
    "学业":   ["文昌", "文曲", "正印"],
    "桃花":   ["桃花", "贪狼", "红鸾", "天喜"],
    "小人":   ["擎羊", "陀罗", "七杀"],
    "贵人":   ["天魁", "天钺", "天乙贵人"],
    "搬家":   ["迁移宫", "驿马"],
    "偏财":   ["偏财", "财帛宫"],
    "正财":   ["正财", "财帛宫"],
    "升职":   ["官禄宫", "正官"],
    "跳槽":   ["迁移宫", "官禄宫"],
    "婚姻":   ["夫妻宫", "红鸾", "天喜"],
}


def extract_metaphysics_tags(message):
    matched = []
    for alias, target_tags in _TAG_ALIASES.items():
        if alias in message:
            matched.append(target_tags[0])
    for tag in _ALL_TAGS:
        if len(tag) >= 2 and tag in message:
            matched.append(tag)
    seen = set()
    result = []
    for t in matched:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result[:5]
