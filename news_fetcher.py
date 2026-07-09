"""Multi-source hot-list fetcher — Bilibili, GitHub, Baidu, news aggregators."""

import re
import httpx
from db import execute, q

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def fetch_bilibili_popular() -> list[dict]:
    """Bilibili popular videos — reliable public API."""
    try:
        resp = httpx.get(
            "https://api.bilibili.com/x/web-interface/popular",
            params={"ps": 20},
            headers=HEADERS,
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
        return []


def fetch_github_trend() -> list[dict]:
    """GitHub Trending — HTML scraping."""
    try:
        resp = httpx.get(
            "https://github.com/trending",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        # Parse h2 > a tags with repo paths
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
        return []


def fetch_tophub() -> list[dict]:
    """Tophub.today — Chinese hot-list aggregator."""
    try:
        resp = httpx.get(
            "https://tophub.today/",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=10,
        )
        resp.raise_for_status()
        # Parse table rows: <td class="al"><a href="..." ...>title</a></td>
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
            # Determine source from URL
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
        return []


def fetch_baidu_hot() -> list[dict]:
    """Baidu hot search — page scraping."""
    try:
        resp = httpx.get(
            "https://top.baidu.com/board?tab=realtime",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=10,
        )
        resp.raise_for_status()
        # Parse hot titles from the page
        titles = re.findall(r'<div[^>]*class="[^"]*c-single-text-ellipsis[^"]*"[^>]*>([^<]+)</div>', resp.text)
        # Backup: try other patterns
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
        return []


def fetch_all_sources() -> list[dict]:
    """Aggregate all sources, deduplicate by title."""
    all_items = []
    for fetcher in [fetch_bilibili_popular, fetch_github_trend, fetch_tophub, fetch_baidu_hot]:
        try:
            items = fetcher()
            all_items.extend(items)
        except Exception:
            pass

    # Dedup by first 15 chars of lowercase title
    seen = set()
    deduped = []
    for item in all_items:
        key = item["title"].lower().strip()[:20]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    # Re-number
    for i, item in enumerate(deduped):
        item["rank"] = i + 1

    return deduped


def fetch_all():
    """Fetch from all sources and replace news_items table."""
    items = fetch_all_sources()
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
