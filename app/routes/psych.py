"""心理学增强 (Psych) API 路由 — 行为标记查询."""

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/api/psych/behavioral-markers")
async def get_behavioral_markers(session_id: str = Query(default="default")):
    """获取最近一次行为标记分析结果."""
    from services.psych.behavioral_markers import get_latest_markers, get_behavioral_context
    markers = get_latest_markers(session_id)
    ctx = get_behavioral_context(session_id)
    return {
        "markers": markers,
        "context": ctx,
    }
