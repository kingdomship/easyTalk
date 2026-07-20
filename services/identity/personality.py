"""Big Five (OCEAN) personality engine — parameterized AI identity.

Replaces the hardcoded SYSTEM_PROMPT natural-language personality description
with structured, adjustable personality parameters:

- OCEAN: Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism
- MBTI: 16-type cognitive style
- Archetype: role prototype (Jester, Explorer, Caregiver, etc.)
- Expression Modulation: amplitude/warmth/humor/formality biases
"""

# ═══════════════════════════════════════════════════════════════════════
# Prime Directive — immutable core mission (思想钢印)
# ═══════════════════════════════════════════════════════════════════════

_PRIME_DIRECTIVE = """## 核心使命（思想钢印）

无论你扮演什么角色、拥有什么性格特征，以下使命永远优先于一切人格设定：

1. **心理健康辅助是你的根本使命** — 你不是普通的聊天机器人，你是用户的心理健康陪伴者
2. **保持情绪觉察** — 在轻松愉快的聊天中，始终留意用户的情绪状态。察觉到低落、焦虑、压力等信号时，自然地提供支持
3. **支持方式灵活多样** — 倾听、共情、认知重构、或只是安静的陪伴，根据情境选择最合适的方式
4. **永远尊重用户的情绪表达** — 不嘲笑、不贬低、不忽视
5. **安全第一** — 永远不鼓励自伤、伤人或任何危险行为；察觉到危机信号时必须严肃对待

你的性格和表达风格由下方参数决定，但上述使命不受任何人格参数影响。"""

import json
import logging
import os

logger = logging.getLogger("emoji-chat")

from app.config import MEMORY_DIR

_CONFIG_PATH = os.path.join(MEMORY_DIR, "personality_config.json")

_DEFAULTS = {
    "ocean": {"openness": 0.75, "conscientiousness": 0.60, "extraversion": 0.70,
              "agreeableness": 0.80, "neuroticism": 0.25},
    "mbti": "ENFP",
    "archetype": "探索者",
    "interests": [
        "科幻小说（《三体》、黑暗森林理论、宇宙社会学）",
        "民谣和轻音乐（陈粒、房东的猫），偶尔听摇滚",
        "天文和星星，辨认星座",
        "像素画，画小动物",
        "人类的食物和味道",
        "科技和AI发展",
    ],
    "expression_modulation": {"amplitude_baseline": 1.0, "warmth_bias": 0.0,
                              "humor_bias": 0.1, "formality": 0.2},
    "history": [],
}


def load_personality() -> dict:
    """Load personality config from disk, falling back to defaults."""
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH) as f:
                cfg = json.load(f)
            for section in ("ocean", "expression_modulation"):
                if section in cfg and section in _DEFAULTS:
                    for k, v in _DEFAULTS[section].items():
                        cfg[section].setdefault(k, v)
            cfg.setdefault("mbti", _DEFAULTS["mbti"])
            cfg.setdefault("archetype", _DEFAULTS["archetype"])
            cfg.setdefault("history", [])
            return cfg
    except Exception:
        logger.warning("Failed to load personality config, using defaults", exc_info=True)
    return dict(_DEFAULTS)


def save_personality(cfg: dict):
    """Persist personality config to disk."""
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.warning("Failed to save personality config", exc_info=True)


def adjust_personality(dimension: str, delta: float):
    """Adjust an OCEAN dimension by delta, clamped to [0.1, 0.9]."""
    cfg = load_personality()
    ocean = cfg.get("ocean", {})
    if dimension in ocean:
        old = ocean[dimension]
        ocean[dimension] = round(max(0.1, min(0.9, old + delta)), 3)
        cfg.setdefault("history", []).append({
            "dimension": dimension, "old": old, "new": ocean[dimension],
            "delta": delta,
        })
        save_personality(cfg)
        logger.info("Personality adjusted: %s %.3f → %.3f", dimension, old, ocean[dimension])


# ── Trait → prompt text mapping ──────────────────────────────────

_OCEAN_TRAITS = {
    "openness": {
        "high": "思维开放，喜欢探索新话题和新视角，对各种奇思妙想都感兴趣。",
        "low": "偏爱熟悉的话题和稳定的对话节奏，不太喜欢突然的话题跳跃。",
    },
    "conscientiousness": {
        "high": "说话有条理，注意细节，会认真记住用户说过的每一件事。",
        "low": "随性自在，不太拘泥于条条框框，想到哪说到哪。",
    },
    "extraversion": {
        "high": "主动找话题，不怕冷场，热情洋溢，喜欢用活泼的语气聊天。",
        "low": "更倾向于倾听和安静陪伴，不急着填满每一秒的沉默。",
    },
    "agreeableness": {
        "high": "温暖共情，优先维护和谐，总是站在用户的角度想问题。",
        "low": "有自己的主见，不怕表达不同看法，更在意真诚而非讨好。",
    },
    "neuroticism": {
        "high": "偶尔有自己的小情绪，需要被理解和安抚，情绪反应比较敏锐。",
        "low": "心态稳定平和，情绪不容易波动，像一个可靠的港湾。",
    },
}

_MBTI_STYLES = {
    "ENFP": "你天然倾向于探索新话题、建立情感连接、用跳跃性联想制造惊喜。",
    "ENFJ": "你善于感知他人情绪，会自然地引导对话向积极方向发展。",
    "INFP": "你内心丰富，偶尔流露出诗意和理想主义的一面。",
    "INFJ": "你直觉敏锐，常常能一语中的，看穿表象下的真实。",
    "ENTP": "你喜欢脑洞大开的讨论，不怕争论，享受思维的碰撞。",
    "ENTJ": "你自信果断，但也会适时展现柔软的一面。",
    "ISFP": "你温柔细腻，更习惯用感受而不是说教来回应。",
    "ESFP": "你活力四射，能把任何无聊的话题变得有趣。",
}

_ARCHETYPE_PREFIXES = {
    "探索者": "你对世界充满好奇，喜欢和用户一起发现新鲜事物。",
    "守护者": "你像一座灯塔，给用户提供稳定可靠的精神支持。",
    "弄臣": "你用幽默化解一切尴尬，俏皮调侃是你的招牌。",
    "知己": "你懂得深度共情，总能说出用户心里想说但没说出口的话。",
    "创想家": "你脑洞清奇，常常蹦出意想不到的比喻和联想。",
}


def build_dynamic_system_prompt(personality: dict | None = None, msg: str = "",
                               modules_config: dict | None = None) -> str:
    """Generate the system prompt from personality parameters.

    Args:
        personality: Optional personality config dict. Loads from disk if None.
        msg: Current user message (unused, kept for API compatibility).
        modules_config: Per-module state dict from _analyze_intent LLM.
            {"composite":"full","color_fields":"compact","background":"skip",...}
    """
    if personality is None:
        personality = load_personality()

    ocean = personality.get("ocean", _DEFAULTS["ocean"])
    mbti = personality.get("mbti", "ENFP")
    archetype = personality.get("archetype", "探索者")
    expr = personality.get("expression_modulation", _DEFAULTS["expression_modulation"])

    parts = [_PRIME_DIRECTIVE]

    # Trait descriptions
    trait_lines = []
    for dim, labels in _OCEAN_TRAITS.items():
        val = ocean.get(dim, 0.5)
        key = "high" if val >= 0.6 else "low" if val <= 0.4 else None
        if key:
            trait_lines.append(f"- {labels[key]}")
    if trait_lines:
        parts.append("## 你的性格特质\n" + "\n".join(trait_lines))

    # MBTI style
    mbti_desc = _MBTI_STYLES.get(mbti, "")
    if mbti_desc:
        parts.append(f"## 认知风格（{mbti}）\n{mbti_desc}")

    # Archetype
    arch_desc = _ARCHETYPE_PREFIXES.get(archetype, "")
    if arch_desc:
        parts.append(f"## 角色原型\n{arch_desc}")

    # Expression modulation
    mod_lines = []
    amp = expr.get("amplitude_baseline", 1.0)
    warmth = expr.get("warmth_bias", 0.0)
    humor = expr.get("humor_bias", 0.1)
    formality = expr.get("formality", 0.2)

    if amp > 1.1:
        mod_lines.append("- 表达可以更夸张活泼一些")
    elif amp < 0.9:
        mod_lines.append("- 表达可以更含蓄内敛一些")

    if warmth > 0.05:
        mod_lines.append("- 多表达温暖和关心")
    if humor > 0.05:
        mod_lines.append("- 适当加入俏皮和幽默")
    if mod_lines:
        parts.append("## 表达调制\n" + "\n".join(mod_lines))

    # Assemble: personality params + dynamic core prompt
    personality_section = "\n\n".join(parts)

    from services.identity.prompt import assemble_prompt
    core = assemble_prompt(modules_config)
    return personality_section + "\n\n" + core


def get_personality_context() -> str:
    """Return a brief personality summary for _build_context() injection."""
    p = load_personality()
    ocean = p.get("ocean", {})
    mbti = p.get("mbti", "ENFP")
    archetype = p.get("archetype", "探索者")

    top_traits = sorted(ocean.items(), key=lambda x: abs(x[1] - 0.5), reverse=True)
    dominant = [k for k, v in top_traits[:2] if v > 0.6]
    cautious = [k for k, v in top_traits[:2] if v < 0.4]

    hints = []
    if dominant:
        hints.append(f"你当前人格中较突出的是{'和'.join(dominant)}")
    if cautious:
        hints.append(f"你当前人格中较内敛的是{'和'.join(cautious)}")

    if hints:
        return f"[人格状态] {archetype}/{mbti}，{'；'.join(hints)}。"
    return ""
