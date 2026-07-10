"""Emotion cache management."""

from fastapi import APIRouter
from app.db import q, execute
from app.routes.chat import _ensure_db

router = APIRouter()


@router.get("/api/emotions")
def list_emotions():
    _ensure_db()
    return q("SELECT * FROM emotion_cache WHERE label NOT LIKE 'exact:%%' ORDER BY use_count DESC")


@router.delete("/api/emotions/{label}")
def delete_emotion(label: str):
    execute("DELETE FROM emotion_cache WHERE label = %s", [label])
    return {"ok": True}
