"""Metaphysics API routes — 命理子系统 8个端点"""
import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import BIRTH_INFO_PATH, atomic_write
from app.tracer import get_request_id
from app.audit import audit_log
from app.token_tracker import record_tokens

logger = logging.getLogger("metaphysics")

router = APIRouter(prefix="/api/metaphysics", tags=["metaphysics"])

# 解读缓存 (内存)
_reading_cache: dict = {}
_reading_cache_lock = None


def _get_cache_lock():
    global _reading_cache_lock
    if _reading_cache_lock is None:
        import threading
        _reading_cache_lock = threading.Lock()
    return _reading_cache_lock


class BirthInfoRequest(BaseModel):
    name: str = "用户"
    gender: str = "女"
    calendar: str = "solar"
    solar_date: str = "2000-01-01"
    lunar_date: dict | None = None
    clock_time: str = "12:00"
    city: str = "北京"
    is_dst_affected: bool = False
    zi_rule: str = "late_zi"


class ReadingRequest(BaseModel):
    type: str = "bazi"  # "bazi" | "ziwei"
    scope: str = "general"
    temp_birth: dict | None = None
    context: str = ""


class HehunRequest(BaseModel):
    other_birth: dict


@router.get("/birth-info")
async def get_birth_info():
    """获取已保存的出生信息"""
    if not os.path.exists(BIRTH_INFO_PATH):
        return {"has_birth_info": False, "birth_info": None}
    try:
        with open(BIRTH_INFO_PATH, "r") as f:
            data = json.load(f)
        return {"has_birth_info": True, "birth_info": data}
    except Exception as e:
        logger.warning("Failed to read birth info: %s", e)
        return {"has_birth_info": False, "birth_info": None}


@router.post("/birth-info")
async def save_birth_info(req: BirthInfoRequest):
    """保存/更新出生信息"""
    birth_info = req.model_dump()
    os.makedirs(os.path.dirname(BIRTH_INFO_PATH), exist_ok=True)
    atomic_write(BIRTH_INFO_PATH, json.dumps(birth_info, ensure_ascii=False, indent=2))

    from services.metaphysics.cache import cache
    cache.invalidate()

    audit_log("save_birth_info", "metaphysics", "保存出生信息",
              metadata={"gender": req.gender, "solar_date": req.solar_date})
    return {"ok": True, "birth_info": birth_info}


@router.get("/bazi")
async def get_bazi():
    """获取八字命盘 (含当前大运流年)"""
    from services.metaphysics.cache import cache
    bazi = await cache.get_bazi_async(include_dynamic=True)
    if not bazi or bazi.get("error"):
        return {"error": True, "error_message": "未填写出生信息，请先在命理面板中填写"}
    return bazi


@router.get("/ziwei")
async def get_ziwei():
    """获取紫微命盘 (含当前大限流年)"""
    from services.metaphysics.cache import cache
    ziwei = await cache.get_ziwei_async(include_dynamic=True)
    if not ziwei or ziwei.get("error"):
        return {"error": True, "error_message": "未填写出生信息，请先在命理面板中填写"}
    return ziwei


@router.get("/full-chart")
async def get_full_chart(request: Request):
    """一次性返回八字+紫微静态层 (面板加载用, 支持ETag)"""
    from services.metaphysics.cache import cache
    birth_hash = cache.get_birth_hash()
    if not birth_hash:
        return {"error": True, "error_message": "未填写出生信息"}

    etag = f'"{birth_hash}"'
    if_none_match = request.headers.get("If-None-Match", "")
    if if_none_match == etag:
        from fastapi.responses import Response
        return Response(status_code=304)

    from services.metaphysics.solar_time import correct_solar_time
    import json
    birth_info = json.load(open(BIRTH_INFO_PATH)) if os.path.exists(BIRTH_INFO_PATH) else None
    if not birth_info:
        return {"error": True, "error_message": "未填写出生信息"}

    from services.metaphysics.calculator import get_full_chart as _get_full_chart
    chart = await _get_full_chart(birth_info)
    return {"chart": chart, "etag": etag}


@router.get("/reading")
async def get_reading(type: str = "bazi", scope: str = "general"):
    """获取已缓存的解读 (从内存缓存或DB读取, 幂等, 不调LLM)"""
    from services.metaphysics.cache import cache
    birth_hash = cache.get_birth_hash()
    if not birth_hash:
        return {"cached": False, "reading_text": None}

    cache_key = hashlib.md5(
        f"{type}:{scope}:{birth_hash}:self".encode()
    ).hexdigest()

    with _get_cache_lock():
        if cache_key in _reading_cache:
            return {"cached": True, "reading_text": _reading_cache[cache_key]}

    from app.db import q
    rows = q(
        """SELECT reading_text FROM metaphysics_reading
           WHERE reading_type=%s AND scope=%s AND is_temp_birth=false
             AND static_chart_hash=%s
           ORDER BY created_at DESC LIMIT 1""",
        [type, scope, birth_hash],
    )
    if rows:
        text = rows[0]["reading_text"]
        with _get_cache_lock():
            _reading_cache[cache_key] = text
        return {"cached": True, "reading_text": text}

    return {"cached": False, "reading_text": None}


@router.post("/reading")
async def trigger_reading(req: ReadingRequest, request: Request):
    """触发新解读 (调LLM, 可传 temp_birth 做临场解读)"""
    from services.metaphysics.cache import cache
    from services.metaphysics.calculator import compute_bazi_from_birth, compute_ziwei_from_birth

    is_temp = req.temp_birth is not None

    if is_temp:
        bazi = compute_bazi_from_birth(req.temp_birth)
        ziwei = compute_ziwei_from_birth(req.temp_birth)
        if bazi.get("error") or ziwei.get("error"):
            raise HTTPException(422, "出生信息校验失败，请检查日期和时间格式")
        chart = {"bazi": bazi, "ziwei": ziwei}
        birth_hash = hashlib.md5(
            json.dumps(req.temp_birth, sort_keys=True).encode()
        ).hexdigest()
    else:
        birth_hash = cache.get_birth_hash()
        if not birth_hash:
            raise HTTPException(400, "未填写出生信息，请先在命理面板填写")
        bazi = cache.get_bazi(include_dynamic=True)
        ziwei = cache.get_ziwei(include_dynamic=True)
        chart = {"bazi": bazi, "ziwei": ziwei}

    # 节流检查: 同一客户端每分钟最多1次
    client_key = hashlib.md5(
        f"{request.client.host}:{request.headers.get('User-Agent', '')}".encode()
    ).hexdigest()
    with _get_cache_lock():
        last_ts = _reading_cache.get(f"_throttle:{client_key}", 0)
        if time.time() - last_ts < 60:
            raise HTTPException(429, "解读频率过高，请稍后再试")
        _reading_cache[f"_throttle:{client_key}"] = time.time()

    # 查缓存 (24h TTL)
    cache_key = hashlib.md5(
        f"{req.type}:{req.scope}:{birth_hash}:{'temp' if is_temp else 'self'}".encode()
    ).hexdigest()
    with _get_cache_lock():
        if cache_key in _reading_cache:
            audit_log("reading_cache_hit", "metaphysics", f"解读缓存命中 {req.type}/{req.scope}")
            return {"reading_text": _reading_cache[cache_key], "is_cached": True}

    # 知识库检索
    from services.metaphysics.knowledge import search_kb, extract_metaphysics_tags
    tags = extract_metaphysics_tags(req.context or req.scope)
    kb_entries = search_kb(tags, limit=5)

    # 用户画像
    user_portrait = ""
    try:
        from services.psych.user_model import get_user_portrait
        user_portrait = get_user_portrait() or ""
    except Exception:
        pass

    # Build prompt
    from services.metaphysics.interpreter import build_reading_prompt
    prompt = build_reading_prompt(chart, req.scope, kb_entries, user_portrait)

    # Call LLM
    from app.utils import get_llm
    try:
        llm = get_llm()
        response = await asyncio.to_thread(llm.invoke, prompt)
        reading_text = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.error("LLM reading failed: %s", e)
        from services.metaphysics.interpreter import build_fallback_reading
        reading_text = build_fallback_reading(chart, req.scope)
        audit_log("reading_llm_failed", "metaphysics", f"解读LLM失败: {str(e)[:100]}")
        return {"reading_text": reading_text, "is_fallback": True}

    # Cache
    with _get_cache_lock():
        _reading_cache[cache_key] = reading_text

    # Persist to DB
    try:
        from app.db import execute
        import json as _json
        execute(
            """INSERT INTO metaphysics_reading
               (request_id, reading_type, scope, is_temp_birth, static_chart_hash,
                reading_text, chart_snapshot)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            [get_request_id(), req.type, req.scope, is_temp, birth_hash,
             reading_text, _json.dumps(chart, ensure_ascii=False)],
        )
    except Exception as e:
        logger.warning("Failed to persist reading: %s", e)

    audit_log("trigger_reading", "metaphysics", f"触发解读 {req.type}/{req.scope}",
              metadata={"is_temp": is_temp, "prompt_len": len(prompt)})

    return {"reading_text": reading_text, "is_cached": False}


@router.post("/hehun")
async def hehun(req: HehunRequest):
    """合盘分析 (返回纯数据, 不调LLM)"""
    from services.metaphysics.cache import cache
    from services.metaphysics.calculator import compute_bazi_from_birth, compute_ziwei_from_birth

    self_bazi = cache.get_bazi(include_dynamic=False)
    self_ziwei = cache.get_ziwei(include_dynamic=False)
    if not self_bazi or self_bazi.get("error"):
        raise HTTPException(400, "请先填写自己的出生信息")

    other_bazi = compute_bazi_from_birth(req.other_birth)
    other_ziwei = compute_ziwei_from_birth(req.other_birth)
    if other_bazi.get("error") or other_ziwei.get("error"):
        raise HTTPException(422, "对方出生信息校验失败")

    from services.metaphysics.ziwei.hepan import compute_hepan
    hepan_result = compute_hepan(self_ziwei, other_ziwei)

    audit_log("hehun", "metaphysics", "合盘分析")

    return {
        "self": {"bazi": self_bazi, "ziwei": self_ziwei},
        "other": {"bazi": other_bazi, "ziwei": other_ziwei},
        "hepan": hepan_result,
    }
