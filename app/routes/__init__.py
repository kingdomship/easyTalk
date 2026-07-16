"""Aggregate all API route modules."""

from fastapi import APIRouter

from app.routes.chat import router as chat_router
from app.routes.emotions import router as emotions_router
from app.routes.diary import router as diary_router
from app.routes.news import router as news_router
from app.routes.memory import router as memory_router
from app.routes.config import router as config_router

router = APIRouter()
router.include_router(chat_router)
router.include_router(emotions_router)
router.include_router(diary_router)
router.include_router(news_router)
router.include_router(memory_router)
router.include_router(config_router)
