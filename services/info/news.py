"""Multi-source hot-list fetcher — Bilibili, GitHub, Baidu, news aggregators."""

import asyncio
import logging
import re
import httpx
from app.db import q, execute

logger = logging.getLogger("emoji-chat")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


async def _fetch_bilibili(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            "https://api.bilibili.com/x/web-interface/popular",
            params={"ps": 20},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for item in data.get("data", {}).get("list", []):
            title = item.get("title", "").strip()
            if not title:
                continue
            bvid = item.get("bvid", "")
            url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
            items.append({
                "title": title,
                "url": url,
                "source": "bilibili",
                "rank": len(items) + 1,
            })
        return items[:15]
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return []


async def _fetch_github(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            "https://github.com/trending",
            headers={"Accept": "text/html"},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        matches = re.findall(
            r'<h2[^>]*>.*?<a[^>]*href="(/[^/"]+/[^/"]+)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL,
        )
        items = []
        seen = set()
        for path, content in matches:
            if "/login" in path:
                continue
            name = re.sub(r'<[^>]+>', '', content).strip()
            name = re.sub(r'\s+', ' ', name).strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            items.append({
                "title": name,
                "url": f"https://github.com{path}",
                "source": "github",
                "rank": len(items) + 1,
            })
        return items[:10]
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return []


async def _fetch_tophub(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            "https://tophub.today/",
            headers={"Accept": "text/html"},
            timeout=10,
        )
        resp.raise_for_status()
        rows = re.findall(
            r'<td[^>]*>\d+</td>\s*<td[^>]*><a[^>]*href="([^"]*)"[^>]*>([^<]+)</a>',
            resp.text,
        )
        items = []
        seen = set()
        for url, title in rows:
            title = title.strip()
            if not title or len(title) < 2 or title in seen:
                continue
            seen.add(title)
            source = "tophub"
            if "weibo" in url:
                source = "weibo"
            elif "zhihu" in url:
                source = "zhihu"
            elif "baidu" in url:
                source = "baidu"
            items.append({
                "title": title,
                "url": url if url.startswith("http") else "",
                "source": source,
                "rank": len(items) + 1,
            })
        return items[:20]
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return []


async def _fetch_baidu(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            "https://top.baidu.com/board?tab=realtime",
            headers={"Accept": "text/html"},
            timeout=10,
        )
        resp.raise_for_status()
        titles = re.findall(
            r'<div[^>]*class="[^"]*c-single-text-ellipsis[^"]*"[^>]*>([^<]+)</div>',
            resp.text,
        )
        if not titles:
            titles = re.findall(r'"word":"([^"]+)"', resp.text)
        items = []
        seen = set()
        for title in titles:
            title = title.strip()
            if not title or len(title) < 2 or title in seen:
                continue
            seen.add(title)
            items.append({
                "title": title,
                "url": f"https://www.baidu.com/s?wd={title}",
                "source": "baidu",
                "rank": len(items) + 1,
            })
        return items[:15]
    except Exception:
        logger.warning("Operation failed", exc_info=True)
        return []


async def _fetch_all_sources() -> list[dict]:
    """Aggregate all sources concurrently, deduplicate by title."""
    async with httpx.AsyncClient(headers=HEADERS) as client:
        results = await asyncio.gather(
            _fetch_bilibili(client),
            _fetch_github(client),
            _fetch_tophub(client),
            _fetch_baidu(client),
        )

    all_items = []
    for items in results:
        all_items.extend(items)

    seen = set()
    deduped = []
    for item in all_items:
        key = item["title"].lower().strip()[:20]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    for i, item in enumerate(deduped):
        item["rank"] = i + 1

    return deduped


async def fetch_all() -> int:
    """Fetch from all sources and replace news_items table."""
    items = await _fetch_all_sources()
    if not items:
        return 0

    execute("DELETE FROM news_items")
    for item in items:
        execute(
            "INSERT INTO news_items (title, url, source, rank) VALUES (%s, %s, %s, %s)",
            [item["title"], item["url"], item["source"], item["rank"]],
        )
    return len(items)


def get_recent_news(limit: int = 10) -> list[dict]:
    """Get recent news for chat context injection."""
    return q("SELECT title, url, source FROM news_items ORDER BY rank ASC LIMIT %s", [limit])


# ── Smart topic recommendation ────────────────────────────────────────────────

# Interest-related KG entity types (subset of profile_types from knowledge_graph.py)
_INTEREST_KG_TYPES = {"hobby", "food", "media", "tech", "activity"}


def get_user_interest_keywords() -> set[str]:
    """Extract user interest keywords from life_domains + knowledge graph.

    Returns empty set for new users — the system degrades gracefully to
    showing general news instead of personalized recommendations.
    """
    keywords: set[str] = set()

    # 1) From life domains: salience > 0.15 → add domain keywords
    try:
        from services.psych.life_domains import DOMAINS, _load
        data = _load()
        for key, dom in DOMAINS.items():
            salience = data.get(key, {}).get("salience", 0)
            if salience > 0.15:
                for kw in dom.get("keywords", []):
                    if len(kw) >= 2:  # skip single-char keywords to reduce noise
                        keywords.add(kw)
    except Exception:
        logger.debug("Failed to load life domains for interest keywords", exc_info=True)

    # 2) From knowledge graph: hobby/food/media/tech/activity entities
    try:
        from services.memory.knowledge_graph import get_current_state
        state = get_current_state()
        for s in state:
            if s.get("type") in _INTEREST_KG_TYPES:
                name = s.get("name", "").strip()
                if len(name) >= 2:
                    keywords.add(name)
    except Exception:
        logger.debug("Failed to load KG for interest keywords", exc_info=True)

    return keywords


def _score_news(items: list[dict], keywords: set[str]) -> list[tuple[int, dict]]:
    """Score news items by keyword overlap. Returns [(score, item), ...] sorted desc."""
    if not keywords:
        return []
    scored = []
    for item in items:
        title = item.get("title", "").lower()
        score = sum(1 for kw in keywords if kw in title)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def get_smart_news_context(idle_min: float = 0) -> str:
    """Build a single-line news hint for system prompt injection.

    Strategy:
    - If user has interests and a news item matches → inject 1 matched item
    - Else if idle > 10 min (returning after a gap) → inject 1 general item
    - Otherwise → empty string (no injection, keeps prompt clean)

    Returns empty string when there's nothing worth injecting.
    """
    items = get_recent_news(20)
    if not items:
        return ""

    keywords = get_user_interest_keywords()

    # Path A: interest-matched news
    if keywords:
        scored = _score_news(items, keywords)
        if scored:
            _, item = scored[0]
            src_label = _source_label(item.get("source", ""))
            return (
                f"\n\n## 你可能感兴趣的新闻（和用户的兴趣相关，自然聊到时可提）\n"
                f"- [{src_label}] {item['title']}"
            )

    # Path B: cold start / idle return — general topic as icebreaker
    if idle_min > 10:
        item = items[0]
        src_label = _source_label(item.get("source", ""))
        return (
            f"\n\n## 闲聊话题（用户刚回来，如果冷场可以自然提起）\n"
            f"- [{src_label}] {item['title']}"
        )

    return ""


def get_suggested_news(matched_limit: int = 3, general_limit: int = 3) -> dict:
    """Return personalized + general news for the frontend topic bubbles API.

    Returns: {"matched": [...], "general": [...]}
    Each item: {"title", "url", "source"}
    """
    items = get_recent_news(30)
    if not items:
        return {"matched": [], "general": []}

    keywords = get_user_interest_keywords()
    matched = []
    general = []

    if keywords:
        scored = _score_news(items, keywords)
        matched = [
            {"title": item["title"], "url": item.get("url", ""), "source": item.get("source", "")}
            for _, item in scored[:matched_limit]
        ]
        # General = top items NOT in matched
        matched_titles = {m["title"] for m in matched}
        general = [
            {"title": item["title"], "url": item.get("url", ""), "source": item.get("source", "")}
            for item in items
            if item["title"] not in matched_titles
        ][:general_limit]
    else:
        general = [
            {"title": item["title"], "url": item.get("url", ""), "source": item.get("source", "")}
            for item in items[:general_limit]
        ]

    return {"matched": matched, "general": general}


def _source_label(source: str) -> str:
    """Human-readable label for a news source."""
    labels = {
        "zhihu": "知乎", "weibo": "微博", "github": "GitHub",
        "bilibili": "B站", "baidu": "百度", "tophub": "热榜",
    }
    return labels.get(source, source)
