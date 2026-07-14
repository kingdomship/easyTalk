"""Emoji Chat — LLM-driven pixel avatar with emotion sequences."""

import logging
import os
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emoji-chat")

from app.routes import router
from app.db import init_db
from services.news import fetch_all
from services.diary import generate_diary
from services.affinity import init_affinity_db
from services.affect import init_affect_db
from services.consciousness_loop import init_loop_db, idle_thought, mood_fluctuation, diary_seed


def _seed_memory():
    """If memory dir is empty, seed from the image's built-in defaults."""
    mem_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory")
    seed_dir = "/app/memory_seed"
    if os.path.isdir(seed_dir) and (not os.path.isdir(mem_dir) or not os.listdir(mem_dir)):
        os.makedirs(mem_dir, exist_ok=True)
        for fname in os.listdir(seed_dir):
            src = os.path.join(seed_dir, fname)
            dst = os.path.join(mem_dir, fname)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)


_CRITICAL_FILES = {
    "user_persona.md": "AI 人设文件，缺失后 AI 将使用默认性格",
    "user_profile.md": "用户档案文件，缺失后 AI 无法了解用户背景",
}
_OPTIONAL_FILES = {
    "conversation_summary.md": "对话摘要（运行一段时间后自动生成）",
    "conversation_archive.jsonl": "对话归档（首次聊天后自动创建）",
}


def _check_memory_files():
    """Verify memory files exist at startup, log warnings for missing ones."""
    mem_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory")

    for fname, desc in _CRITICAL_FILES.items():
        path = os.path.join(mem_dir, fname)
        if not os.path.exists(path):
            logger.warning("缺少关键文件: %s — %s", fname, desc)

    for fname, desc in _OPTIONAL_FILES.items():
        path = os.path.join(mem_dir, fname)
        if not os.path.exists(path):
            logger.info("可选文件尚未创建: %s — %s", fname, desc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_memory()
    _check_memory_files()
    init_db()
    init_affinity_db()
    init_affect_db()
    init_loop_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(generate_daily_diary, "cron", hour=4, minute=0)
    scheduler.add_job(fetch_all_news, "cron", hour=7, minute=0)
    scheduler.add_job(idle_thought, "cron", minute="*/5")
    scheduler.add_job(mood_fluctuation, "cron", minute="*/30")
    scheduler.add_job(diary_seed, "cron", minute="0")
    scheduler.start()
    yield
    scheduler.shutdown()


def generate_daily_diary():
    """Generate diary for yesterday."""
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    generate_diary(yesterday)


async def fetch_all_news():
    await fetch_all()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
