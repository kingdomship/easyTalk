"""Emoji Chat — LLM-driven pixel avatar with emotion sequences."""

import logging
import os
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emoji-chat")

from app.routes import router
from app.db import init_db
from app.utils import get_background_executor
from services.info.news import fetch_all
from services.reflection.diary import generate_diary, generate_user_diary
from services.emotion.affinity import init_affinity_db
from services.emotion.affect import init_affect_db
from services.reflection.consciousness_loop import init_loop_db, idle_thought, mood_fluctuation, diary_seed, system2_consolidation
from services.emotion.salience import init_salience_db
from services.drive.engine import init_drive_db, drive_heartbeat
from app.cleanup import cleanup_old_data
from services.cognition.predictive_agent import offline_analysis
from app.config import MEMORY_DIR


def _seed_memory():
    """If memory dir is empty, seed from the image's built-in defaults."""
    mem_dir = MEMORY_DIR
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
    mem_dir = MEMORY_DIR

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
    init_salience_db()
    init_drive_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(generate_daily_diary, "cron", hour=4, minute=0)
    scheduler.add_job(fetch_all_news, "cron", hour=7, minute=0)
    scheduler.add_job(idle_thought, "cron", minute="*/5")
    scheduler.add_job(mood_fluctuation, "cron", minute="*/30")
    scheduler.add_job(diary_seed, "cron", minute="0")
    scheduler.add_job(cleanup_old_data, "cron", hour=3, minute=7)
    scheduler.add_job(offline_analysis, "cron", minute="*/7")
    scheduler.add_job(system2_consolidation, "cron", minute="*/23")
    scheduler.add_job(drive_heartbeat, "cron", minute="*/10")
    scheduler.start()

    # ── Catch-up: fill gaps from downtime ──────────────────────
    from app.catchup import catchup_mood, catchup_drives
    catchup_mood()                                          # fast: inline
    catchup_drives()                                        # fast: inline
    get_background_executor().submit(_run_diary_catchup)    # slow: thread
    # ────────────────────────────────────────────────────────────

    yield
    scheduler.shutdown()
    executor = get_background_executor()
    executor.shutdown(wait=False)


def _run_diary_catchup():
    """Fire-and-forget diary catch-up for background thread."""
    from app.catchup import catchup_diaries
    try:
        catchup_diaries()
    except Exception:
        logger.warning("[catchup] Diary bg task failed", exc_info=True)


def generate_daily_diary():
    """Generate diaries for yesterday — AI + user perspectives."""
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    generate_diary(yesterday)
    generate_user_diary(yesterday)


async def fetch_all_news():
    await fetch_all()


app = FastAPI(lifespan=lifespan)
app.include_router(router)


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith((".js", ".css")):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app.add_middleware(CacheControlMiddleware)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
