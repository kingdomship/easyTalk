"""LLM provider configuration — single source of truth for base_url, model, api_key.

Supports 11 built-in providers + custom, with persistence to memory/llm_config.json.
Env vars provide overrides for containerized deployments.
"""

import json
import logging
import os

from pydantic import BaseModel

from app.config import MEMORY_DIR

logger = logging.getLogger("emoji-chat")

LLM_CONFIG_PATH = os.path.join(MEMORY_DIR, "llm_config.json")

# ── Provider presets ─────────────────────────────────────────────

PROVIDER_PRESETS: dict[str, dict] = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o3-mini"],
    },
    "moonshot": {
        "name": "Moonshot (月之暗面)",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "zhipu": {
        "name": "Zhipu AI (智谱)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
        "models": ["glm-4", "glm-4-flash", "glm-4v", "glm-4-plus"],
    },
    "qwen": {
        "name": "Qwen (通义千问)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
    },
    "doubao": {
        "name": "Doubao (豆包)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-pro-32k",
        "models": ["doubao-pro-4k", "doubao-pro-8k", "doubao-pro-32k", "doubao-lite-4k"],
    },
    "baichuan": {
        "name": "Baichuan (百川)",
        "base_url": "https://api.baichuan-ai.com/v1",
        "default_model": "baichuan4",
        "models": ["baichuan4", "baichuan4-turbo", "baichuan3-turbo"],
    },
    "minimax": {
        "name": "MiniMax (海螺)",
        "base_url": "https://api.minimax.chat/v1",
        "default_model": "abab6.5s-chat",
        "models": ["abab6.5s-chat", "abab5.5-chat"],
    },
    "yi": {
        "name": "Yi (零一万物)",
        "base_url": "https://api.lingyiwanwu.com/v1",
        "default_model": "yi-large",
        "models": ["yi-large", "yi-medium", "yi-spark"],
    },
    "stepfun": {
        "name": "StepFun (阶跃星辰)",
        "base_url": "https://api.stepfun.com/v1",
        "default_model": "step-1-8k",
        "models": ["step-1-8k", "step-1-32k", "step-2-16k"],
    },
    "openrouter": {
        "name": "OpenRouter (通用网关)",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o",
        "models": [
            "openai/gpt-4o", "openai/gpt-4o-mini",
            "anthropic/claude-sonnet-4-6", "anthropic/claude-opus-4-7",
            "google/gemini-2.5-pro", "google/gemini-2.5-flash",
            "meta-llama/llama-4-maverick",
        ],
    },
    "custom": {
        "name": "Custom (自定义)",
        "base_url": "",
        "default_model": "",
        "models": [],
    },
}


# ── Config model ──────────────────────────────────────────────────

class LLMConfig(BaseModel):
    api_key: str = ""
    base_url: str = PROVIDER_PRESETS["deepseek"]["base_url"]
    model: str = PROVIDER_PRESETS["deepseek"]["default_model"]
    provider: str = "deepseek"


# ── Persistence ───────────────────────────────────────────────────

def _migrate_old_api_key_file() -> str | None:
    """One-time migration: read api_key.txt if llm_config.json doesn't exist."""
    from app.config import APIKEY_PATH
    try:
        if os.path.exists(APIKEY_PATH):
            with open(APIKEY_PATH) as f:
                key = f.read().strip()
                if key:
                    return key
    except Exception:
        pass
    return None


def load_llm_config() -> LLMConfig:
    """Load LLM config with priority: JSON file > env vars > defaults.

    API key resolution order:
      1. llm_config.json (saved via settings UI)
      2. LLM_API_KEY env var
      3. DEEPSEEK_API_KEY env var (backward compat)
      4. Old api_key.txt file (auto-migrated)
    """
    config = LLMConfig()

    # 1. Try JSON config file
    if os.path.exists(LLM_CONFIG_PATH):
        try:
            with open(LLM_CONFIG_PATH) as f:
                data = json.load(f)
            config = LLMConfig(**data)
        except Exception:
            logger.warning("Failed to load llm_config.json, using defaults", exc_info=True)

    # 2. Env var overrides (for containerized deployments)
    env_base_url = os.getenv("LLM_BASE_URL")
    if env_base_url:
        config.base_url = env_base_url

    env_model = os.getenv("LLM_MODEL")
    if env_model:
        config.model = env_model

    # 3. API key: env vars override file
    env_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if env_key:
        config.api_key = env_key
    elif not config.api_key:
        # 4. Migrate old api_key.txt
        migrated = _migrate_old_api_key_file()
        if migrated:
            config.api_key = migrated
            # Persist to new format so migration only runs once
            save_llm_config(config)

    # 5. If provider is set but base_url/model are empty, fill from preset
    if config.provider in PROVIDER_PRESETS and config.provider != "custom":
        preset = PROVIDER_PRESETS[config.provider]
        if not config.base_url:
            config.base_url = preset["base_url"]
        if not config.model:
            config.model = preset["default_model"]

    return config


def save_llm_config(config: LLMConfig):
    """Persist config to JSON file."""
    os.makedirs(os.path.dirname(LLM_CONFIG_PATH), exist_ok=True)
    with open(LLM_CONFIG_PATH, "w") as f:
        json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
