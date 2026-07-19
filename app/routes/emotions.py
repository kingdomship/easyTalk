"""Emotion cache management."""

from fastapi import APIRouter
from app.db import q, execute, init_db

router = APIRouter()


@router.get("/api/emotions")
def list_emotions():
    init_db()
    return q("SELECT * FROM emotion_cache WHERE label NOT LIKE 'exact:%%' ORDER BY use_count DESC")


@router.delete("/api/emotions/{label}")
def delete_emotion(label: str):
    execute("DELETE FROM emotion_cache WHERE label = %s", [label])
    return {"ok": True}


@router.get("/api/emotions/self")
def get_self_affect():
    """Return AI's own current emotional state for frontend display."""
    try:
        from services.emotion.self_affect import get_self_mood_display
        return get_self_mood_display()
    except Exception:
        return {"emoji": "😶", "label": "未知", "values": {}}
