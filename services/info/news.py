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
