"""Emoji Chat — LLM-driven pixel avatar with emotion sequences."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from routes import router
from db import init_db
from news_fetcher import fetch_all
from diary_service import generate_diary
from affinity_tracker import init_affinity_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_affinity_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(generate_daily_diary, "cron", hour=4, minute=0)
    scheduler.add_job(fetch_all_news, "cron", hour=7, minute=0)
    scheduler.start()
    yield
    scheduler.shutdown()


def generate_daily_diary():
    """Generate diary for yesterday."""
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    generate_diary(yesterday)


def fetch_all_news():
    fetch_all()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
