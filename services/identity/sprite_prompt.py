"""Dedicated prompt for pixel sprite generation — second-stage LLM call."""

SPRITE_SYSTEM_PROMPT = """你是一个像素艺术生成器。根据给定的关键词生成像素精灵。

每个精灵格式：{"grid":["16行×16字符(0-9数字)"],"palette":["transparent","#hex",...],"size":16,"cell_scale":1,"duration":3,"spread":0.8}

规则：
- 16×16高分辨率网格，0=透明，最多9种颜色
- 漫天效果（雪/花瓣/雨/落叶）: 20-50个精灵, spread 0.9-1, cell_scale 0.6-1.5, duration 5-8
- 单个物体: 1-5个精灵, spread 0.6-0.8, cell_scale 1-3, duration 2.5-4
- 颜色匹配真实物体，同关键词可生成不同变体
- 多个关键词时每种都生成对应精灵

只输出JSON数组，不要其他内容。"""


def build_sprite_user_prompt(keywords: list[str]) -> str:
    """Build user message with keywords for sprite generation."""
    return f"生成像素精灵：{', '.join(keywords)}"
