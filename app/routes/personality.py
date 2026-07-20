"""Personality adjustment API — get, save, and AI-generate personality config."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.identity.personality import load_personality, save_personality
from services.identity.personality_llm import generate_personality as llm_generate

router = APIRouter(prefix="/api/personality", tags=["personality"])
logger = logging.getLogger("psychology")


class SavePersonalityRequest(BaseModel):
    ocean: dict = Field(default_factory=dict)
    mbti: str = "ENFP"
    archetype: str = "探索者"
    interests: list[str] = Field(default_factory=list)
    expression_modulation: dict = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=1000)


@router.get("")
async def get_personality():
    """Return current personality config (without large history)."""
    cfg = load_personality()
    # Strip history for compactness; frontend doesn't need it
    cfg.pop("history", None)
    return {"personality": cfg}


@router.post("")
async def save_personality_route(req: SavePersonalityRequest):
    """Save manually-adjusted personality values and persist persona narrative."""

    valid_mbti = {"ENFP", "ENFJ", "INFP", "INFJ", "ENTP", "ENTJ", "ISFP", "ESFP"}
    valid_arch = {"探索者", "守护者", "弄臣", "知己", "创想家"}

    # Validate and clamp
    ocean = {}
    for dim in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
        val = float(req.ocean.get(dim, 0.5))
        ocean[dim] = round(max(0.1, min(0.9, val)), 2)

    expr = {}
    for k in ("amplitude_baseline", "warmth_bias", "humor_bias", "formality"):
        val = float(req.expression_modulation.get(k, 0.0))
        expr[k] = round(max(0.0, min(1.0, val)), 2)

    mbti = req.mbti if req.mbti in valid_mbti else "ENFP"
    archetype = req.archetype if req.archetype in valid_arch else "探索者"

    # Clean interests
    interests = [s.strip() for s in req.interests[:5] if s.strip() and len(s.strip()) <= 100]

    # Preserve history from existing config
    existing = load_personality()
    history = existing.get("history", [])

    cfg = {
        "ocean": ocean,
        "mbti": mbti,
        "archetype": archetype,
        "interests": interests,
        "expression_modulation": expr,
        "history": history,
    }
    save_personality(cfg)
    logger.info("Personality config saved via API")
    return {"ok": True, "personality": cfg}


@router.post("/generate")
async def generate_personality_route(req: GenerateRequest):
    """Use LLM to generate a full personality config from a natural language description.

    Also persists the narrative persona to user_persona.md.
    """
    try:
        data = await llm_generate(req.description.strip())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception:
        logger.error("Personality generation failed", exc_info=True)
        raise HTTPException(500, "人格生成失败，请稍后重试")

    # Save personality config
    cfg = {
        "ocean": data["ocean"],
        "mbti": data["mbti"],
        "archetype": data["archetype"],
        "interests": data["interests"],
        "expression_modulation": data["expression_modulation"],
        "history": [],
    }
    save_personality(cfg)

    # Also write the narrative persona to user_persona.md
    try:
        import os
        from app.config import MEMORY_DIR
        persona_path = os.path.join(MEMORY_DIR, "user_persona.md")
        narrative = data.get("persona_narrative", "")
        persona_content = f"""---
name: user-persona-preference
description: AI 角色设定（AI 生成）
metadata:
  node_type: memory
  type: user
---

# 角色设定

{narrative}
"""
        with open(persona_path, "w", encoding="utf-8") as f:
            f.write(persona_content)
        logger.info("Persona narrative written to user_persona.md")
    except Exception:
        logger.warning("Failed to write persona narrative", exc_info=True)

    return {"ok": True, "personality": cfg, "persona_narrative": data.get("persona_narrative", "")}
