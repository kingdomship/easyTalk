"""Style distillation API endpoints — upload, analyze, list, switch, delete."""

import logging
import os
import re

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from services.distill.file_parser import parse_chat_file
from services.distill.analyzer import analyze_style
from services.distill.profile_store import (
    list_profiles,
    get_profile,
    save_profile,
    get_active_profile,
    delete_profile,
    activate_profile,
    deactivate_all,
)

router = APIRouter(prefix="/api/distill", tags=["distill"])
logger = logging.getLogger("psychology")

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {".txt", ".json"}

# ── Simple in-memory rate limiter ──────────────────────────────
import time
from collections import defaultdict

_upload_times: dict[str, list[float]] = defaultdict(list)
_RATE_WINDOW = 60   # seconds
_RATE_MAX = 5       # max uploads per window


def _check_rate_limit(key: str = "default"):
    now = time.time()
    window = now - _RATE_WINDOW
    _upload_times[key] = [t for t in _upload_times[key] if t > window]
    _upload_times[key].append(now)
    return len(_upload_times[key]) <= _RATE_MAX
_ID_PATTERN = re.compile(r"^[a-f0-9]{1,64}$")


def _validate_profile_id(profile_id: str):
    if not _ID_PATTERN.match(profile_id):
        raise HTTPException(400, f"无效的 profile_id: {profile_id}")


def _sanitize_text(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("﻿", "")  # BOM
    return text.strip()


@router.post("/upload")
async def upload_and_analyze(
    file: UploadFile = File(...),
    name: str = Form("未命名风格"),
):
    """Upload a chat history file, analyze the style, and create a profile."""
    # ── Rate limit check ──
    if not _check_rate_limit():
        raise HTTPException(429, "请求过于频繁，请稍后再试（每分钟最多 5 次上传）")

    # ── Validate file extension ──
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"不支持的文件格式: {ext}，仅支持 {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── Validate file size ──
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            400,
            f"文件大小超过限制 (最大 {MAX_UPLOAD_SIZE // 1024 // 1024}MB)",
        )

    # ── Validate encoding ──
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "文件编码不是 UTF-8，请转换后重试")

    # ── Sanitize ──
    text = _sanitize_text(text)
    if not text:
        raise HTTPException(400, "文件内容为空")

    safe_name = _sanitize_text(name.strip()) or "未命名风格"

    # ── Parse ──
    source_type = "txt" if ext == ".txt" else "json"
    messages = parse_chat_file(text, source_type)
    target_count = sum(1 for m in messages if m.get("role") == "target")

    if target_count < 3:
        raise HTTPException(
            400,
            f"有效发言不足 (需要至少 3 条目标人物的消息，当前检测到 {target_count} 条)。请确认聊天记录中包含足够多目标人物的发言。",
        )

    # ── Analyze ──
    try:
        profile = analyze_style(messages, safe_name, source_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        logger.error("Unexpected distillation error", exc_info=True)
        raise HTTPException(500, f"风格分析失败: {str(e)}")

    # ── Store ──
    try:
        save_profile(profile)
    except OSError as e:
        raise HTTPException(500, f"保存风格人设失败: {str(e)}")

    return {
        "ok": True,
        "profile": profile.to_dict(),
        "stats": {
            "total_messages": len(messages),
            "target_messages": target_count,
        },
    }


@router.get("/profiles")
async def api_list_profiles():
    """List all saved style profiles (without raw_analysis for compactness)."""
    profiles = list_profiles()
    summary = []
    for p in profiles:
        d = p.to_dict()
        d.pop("raw_analysis", None)
        summary.append(d)
    return {"profiles": summary}


@router.get("/profiles/{profile_id}")
async def api_get_profile(profile_id: str):
    """Get a single profile with full details including raw analysis."""
    _validate_profile_id(profile_id)
    profile = get_profile(profile_id)
    if profile is None:
        raise HTTPException(404, "未找到该风格人设")
    return {"profile": profile.to_dict()}


@router.post("/profiles/{profile_id}/activate")
async def api_activate_profile(profile_id: str):
    """Activate a style profile for use in conversations."""
    _validate_profile_id(profile_id)
    result = activate_profile(profile_id)
    if result is None:
        raise HTTPException(404, "未找到该风格人设")
    d = result.to_dict()
    d.pop("raw_analysis", None)
    return {"ok": True, "active": d}


@router.post("/deactivate")
async def api_deactivate():
    """Deactivate style imitation, return to default AI style."""
    deactivate_all()
    return {"ok": True}


@router.delete("/profiles/{profile_id}")
async def api_delete_profile(profile_id: str):
    """Delete a style profile."""
    _validate_profile_id(profile_id)
    ok = delete_profile(profile_id)
    if not ok:
        raise HTTPException(404, "未找到该风格人设")
    return {"ok": True}


@router.get("/active")
async def api_get_active():
    """Get the currently active profile, if any."""
    active = get_active_profile()
    if active is None:
        return {"active": None}
    d = active.to_dict()
    d.pop("raw_analysis", None)
    return {"active": d}
