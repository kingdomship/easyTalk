"""Config endpoints for runtime settings like API key and LLM provider.

API key is persisted to llm_config.json under the memory volume mount,
so it survives container restarts.
"""

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import APIKEY_PATH
from app.utils import read_api_key, reset_llm
from app.audit import audit_log
from app.llm_config import (
    load_llm_config, save_llm_config, LLMConfig, PROVIDER_PRESETS,
)

router = APIRouter()
logger = logging.getLogger("emoji-chat")


# ── Pydantic models ──────────────────────────────────────────────

class ApiKeyRequest(BaseModel):
    api_key: str


class LLMConfigRequest(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    provider: str = "deepseek"
    visual_api_key: str = ""
    visual_base_url: str = ""
    visual_model: str = ""


# ── New full config endpoints ────────────────────────────────────

@router.get("/api/config/llm")
def get_llm_config():
    """Return current LLM config (api_key masked) + provider presets list."""
    config = load_llm_config()
    masked = _mask_key(config.api_key)
    vis_masked = _mask_key(config.visual.api_key) if config.visual.api_key else None
    return {
        "api_key": masked,
        "has_api_key": bool(config.api_key),
        "base_url": config.base_url,
        "model": config.model,
        "provider": config.provider,
        "presets": PROVIDER_PRESETS,
        "visual": {
            "api_key": vis_masked,
            "has_api_key": bool(config.visual.api_key),
            "base_url": config.visual.base_url,
            "model": config.visual.model,
        },
    }


@router.post("/api/config/llm")
def set_llm_config(req: LLMConfigRequest):
    """Save full LLM configuration (provider, base_url, model, api_key)."""
    config = LLMConfig(
        api_key=req.api_key.strip(),
        base_url=req.base_url.strip(),
        model=req.model.strip(),
        provider=req.provider,
    )
    # Fill blanks from provider preset
    preset = PROVIDER_PRESETS.get(config.provider)
    if preset and config.provider != "custom":
        if not config.base_url:
            config.base_url = preset["base_url"]
        if not config.model:
            config.model = preset["default_model"]

    # Visual sub-config
    if req.visual_api_key:
        config.visual.api_key = req.visual_api_key.strip()
    if req.visual_base_url:
        config.visual.base_url = req.visual_base_url.strip()
    if req.visual_model:
        config.visual.model = req.visual_model.strip()

    save_llm_config(config)
    reset_llm()
    audit_log("save_config", "config",
              detail=f"provider={config.provider}, model={config.model}",
              metadata={"visual_model": config.visual.model})
    logger.info("LLM config saved: provider=%s, model=%s, visual=%s",
                config.provider, config.model, config.visual.model)
    return {"ok": True}


# ── Legacy API key endpoints (backward compatible) ───────────────

@router.post("/api/config/apikey")
def set_api_key(req: ApiKeyRequest):
    """Legacy endpoint — saves API key only, keeps other config unchanged."""
    config = load_llm_config()
    key = req.api_key.strip()

    if key:
        config.api_key = key
    else:
        config.api_key = ""

    save_llm_config(config)
    reset_llm()
    audit_log("save_api_key", "config")
    return {"ok": True, "has_custom_key": bool(key)}


@router.get("/api/config/apikey")
def get_api_key_status():
    """Legacy endpoint — returns masked API key status."""
    key = read_api_key()
    return {"has_custom_key": bool(key), "api_key": _mask_key(key)}


# ── Helpers ──────────────────────────────────────────────────────

def _mask_key(key: str | None) -> str | None:
    """Mask API key for safe display."""
    if not key:
        return None
    if len(key) > 12:
        return key[:6] + "****" + key[-4:]
    return key[:3] + "****"
