"""News endpoints."""

from fastapi import APIRouter
from app.db import q
from app.routes.chat import _ensure_db
from services.news import fetch_all

router = APIRouter()


@router.get("/api/news")
def list_news(limit: int = 30):
    _ensure_db()
    return q("SELECT * FROM news_items ORDER BY rank ASC LIMIT %s", [limit])


@router.post("/api/news/fetch")
async def trigger_news_fetch():
    _ensure_db()
    count = await fetch_all()
    return {"ok": True, "count": count}


@router.get("/api/news/topics")
def news_topics(limit: int = 4):
    _ensure_db()
    rows = q("SELECT title, source FROM news_items ORDER BY rank ASC LIMIT %s", [limit])
    topics = []
    for r in rows:
        title = r["title"]
        if "？" in title or "?" in title:
            prompt = title[:40]
        else:
            prompt = f"你怎么看「{title[:25]}」？"
        topics.append({"prompt": prompt, "source": r["source"]})
    return topics
