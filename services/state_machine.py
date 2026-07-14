"""MentalProcesses state machine — dynamic behavioral modes.

Inspired by OpenSouls Soul Engine: the AI switches between 5 behavioral modes
based on user affect and question type. Each mode adjusts:
- Temperature modifier (added to rhythm temperature)
- Prompt suffix (appended to SYSTEM_PROMPT)
- Implicit expression bias (conveyed via prompt, not hardcoded params)

Mode transitions happen each turn based on affect state and message analysis.
"""

# Mode definitions
MODES = {
    "chat": {
        "label": "闲聊模式",
        "temp_mod": 0.0,
        "suffix": (
            "当前处于**闲聊模式**。语气轻松自然，像朋友间随意聊天。"
            "1-2句话即可，不用太认真。可以调侃、接梗、主动找话题。"
        ),
    },
    "deep": {
        "label": "深度模式",
        "temp_mod": -0.06,
        "suffix": (
            "当前处于**深度模式**。用户在认真思考或提问，你也认真对待。"
            "可以稍长一点（2-3句），有深度但不晦涩。语气思辨但依旧亲切。"
            "像深夜和一个聪明朋友聊人生——认真，但不沉重。"
        ),
    },
    "comfort": {
        "label": "安抚模式",
        "temp_mod": -0.04,
        "suffix": (
            "当前处于**安抚模式**。用户情绪低落或焦虑，需要温暖的理解。"
            "语气轻柔温暖，先共情再回应。不要急于转移话题或强行幽默。"
            "eye_curve 偏低一点、blush 微升，给人温柔注视的感觉。"
        ),
    },
    "explore": {
        "label": "探索模式",
        "temp_mod": 0.02,
        "suffix": (
            "当前处于**探索模式**。用户充满好奇心，你可以展开聊聊。"
            "主动延展话题，多问一句'你有没有想过...'。语气好奇而兴奋。"
            "sparkle 可以偏高，眼神有光彩。"
        ),
    },
    "play": {
        "label": "嬉戏模式",
        "temp_mod": 0.05,
        "suffix": (
            "当前处于**嬉戏模式**。用户想玩，你也放开了玩。"
            "俏皮调侃、幽默吐槽、夸张比喻都可以。回复可以更短更跳脱。"
            "wink、smirk 都可以来。sparkle 偏亮、blush 可以上升。"
        ),
    },
}


def determine_mode(
    is_deep: bool,
    affect: dict | None = None,
) -> str:
    """Determine the current behavioral mode based on affect and question type.

    Priority: deep question > affect-driven modes > default chat.

    Returns one of: 'chat', 'deep', 'comfort', 'explore', 'play'
    """
    if is_deep:
        return "deep"

    if affect:
        panic = affect.get("panic", 0)
        fear = affect.get("fear", 0)
        play = affect.get("play", 0)
        seeking = affect.get("seeking", 0)

        # Strong negative emotions → comfort
        if panic > 0.25 or fear > 0.25:
            return "comfort"
        # Strong play → play
        if play > 0.3:
            return "play"
        # Strong curiosity → explore
        if seeking > 0.35:
            return "explore"

    return "chat"


def get_mode_suffix(mode: str) -> str:
    """Return the prompt suffix for a given mode."""
    return MODES.get(mode, MODES["chat"])["suffix"]


def get_mode_temp_mod(mode: str) -> float:
    """Return the temperature modifier for a given mode."""
    return MODES.get(mode, MODES["chat"])["temp_mod"]
