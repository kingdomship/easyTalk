"""LLM-powered personality generation — converts natural language descriptions
into structured OCEAN + MBTI + Archetype + Expression Modulation values.

Called by the /api/personality/generate endpoint.
"""

import json
import logging

logger = logging.getLogger("psychology")

_PERSONALITY_GEN_PROMPT = """你是一个人格心理学专家。根据用户对理想AI角色的描述，生成结构化的人格参数。

输出仅包含 JSON，不要有其他文字：

{
  "ocean": {
    "openness": 0.0-1.0,
    "conscientiousness": 0.0-1.0,
    "extraversion": 0.0-1.0,
    "agreeableness": 0.0-1.0,
    "neuroticism": 0.0-1.0
  },
  "mbti": "ENFP",
  "archetype": "探索者",
  "interests": ["兴趣1", "兴趣2", "兴趣3"],
  "expression_modulation": {
    "amplitude_baseline": 0.0-1.0,
    "warmth_bias": 0.0-1.0,
    "humor_bias": 0.0-1.0,
    "formality": 0.0-1.0
  },
  "persona_narrative": "一段200字以内的角色叙事描述，用第一人称"
}

维度说明：
- openness（经验开放性）: 0=保守传统 1=好奇探索
- conscientiousness（尽责性）: 0=随性自由 1=严谨有条理
- extraversion（外向性）: 0=内敛安静 1=外向活泼
- agreeableness（宜人性）: 0=直言不讳 1=温暖共情
- neuroticism（情绪敏感性）: 0=稳定平和 1=敏感情绪化
- amplitude_baseline: 0=含蓄内敛 1=夸张外放
- warmth_bias: 0=冷静理性 1=温暖关怀
- humor_bias: 0=严肃认真 1=俏皮幽默
- formality: 0=随性口语 1=正式考究

MBTI 类型：ENFP / ENFJ / INFP / INFJ / ENTP / ENTJ / ISFP / ESFP
角色原型：探索者 / 守护者 / 弄臣 / 知己 / 创想家

注意：
- 数值要有区分度，不要都放在 0.5 附近
- 根据用户描述合理推断，不要硬套模板
- 角色原型和 MBTI 应该与数值一致
- 兴趣列表 3-5 个，要具体自然"""


def generate_personality_sync(description: str) -> dict:
    """Call LLM to generate full personality config from user description.

    Returns a dict suitable for saving as personality_config.json.
    Includes both parametric values and a narrative persona description.
    """
    from app.utils import get_llm, get_llm_model

    client = get_llm()
    if client is None:
        raise RuntimeError("LLM client not available")

    resp = client.chat.completions.create(
        model=get_llm_model(),
        messages=[
            {"role": "system", "content": _PERSONALITY_GEN_PROMPT},
            {"role": "user", "content": description.strip()},
        ],
        temperature=0.3,
        max_tokens=800,
        timeout=20.0,
    )

    raw = resp.choices[0].message.content.strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise ValueError(f"LLM response does not contain valid JSON: {raw[:200]}")

    data = json.loads(raw[start:end])

    # Validate and clamp OCEAN values
    ocean = data.get("ocean", {})
    dims = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
    clean_ocean = {}
    for d in dims:
        clean_ocean[d] = round(max(0.1, min(0.9, float(ocean.get(d, 0.5)))), 2)

    # Validate expression modulation
    expr = data.get("expression_modulation", {})
    clean_expr = {}
    for k in ["amplitude_baseline", "warmth_bias", "humor_bias", "formality"]:
        clean_expr[k] = round(max(0.0, min(1.0, float(expr.get(k, 0.0)))), 2)

    # Validate MBTI
    valid_mbti = {"ENFP", "ENFJ", "INFP", "INFJ", "ENTP", "ENTJ", "ISFP", "ESFP"}
    mbti = data.get("mbti", "ENFP")
    if mbti not in valid_mbti:
        mbti = "ENFP"

    # Validate archetype
    valid_arch = {"探索者", "守护者", "弄臣", "知己", "创想家"}
    archetype = data.get("archetype", "探索者")
    if archetype not in valid_arch:
        archetype = "探索者"

    # Interests
    interests = []
    for item in data.get("interests", [])[:5]:
        s = str(item).strip()
        if s and len(s) <= 100:
            interests.append(s)

    # Persona narrative
    narrative = str(data.get("persona_narrative", ""))[:300]

    return {
        "ocean": clean_ocean,
        "mbti": mbti,
        "archetype": archetype,
        "interests": interests,
        "expression_modulation": clean_expr,
        "persona_narrative": narrative,
    }


async def generate_personality(description: str) -> dict:
    """Async wrapper for generate_personality_sync."""
    import asyncio
    return await asyncio.to_thread(generate_personality_sync, description)
