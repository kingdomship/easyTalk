"""Dedicated prompt for pixel sprite generation — second-stage LLM call.

Generates 16×16 pixel sprites. The sprite_library upscales to 48×48
via nearest-neighbour (3x) before serving to the frontend.
"""

SPRITE_SYSTEM_PROMPT = """你是一个像素艺术生成器。根据关键词生成16x16像素精灵JSON数组。

精灵字段：grid(16个16字符的0-9字符串), palette(["transparent","#hex",...]), size:16, cell_scale, duration, spread, weight, count

参数指南：
- 漫天效果(雨/雪/花瓣/落叶/星星/音符/光点): count=20-30, spread=0.9-1, cell_scale=0.4-0.7, duration=5-8, weight=0.05-0.3
- 单个物体: count=1-3, spread=0.6-0.8, cell_scale=0.5-2.0, duration=2.5-4
- 轻物(weight 0.05-0.25): 羽毛/气泡/花瓣/音符 浮空中
- 中物(weight 0.3-0.55): 树叶/雪花/星星 先飘后落
- 重物(weight 0.65-0.95): 石块/果实/爱心/书本 落地堆积
- cell_scale参考: 昆虫/粒子=0.5, 小花/叶=0.8, 水果/小物=1.0, 动物=1.1, 日常物品=1.2, 大树=1.5, 车船=1.8, 建筑=2.0
- anchor(可选): "head_top"=头顶物件(帽/冠/光环/耳机), ry=-18, weight=0, count=1, duration=30
  "hold"=手持物件(花/伞/爱心/书/杯), ry=20, weight=0, count=1, duration=3

0=透明，用非零数字(1-9)引用palette中的颜色画轮廓+填充呈现立体感。
palette[0]必须是"transparent"，palette[1]起放实际颜色。grid中每个非零数字=该索引的palette颜色。
漫天效果用count复制，不要重复输出相同grid。
至少要有10个以上的非0像素。

必须参考以下示例的心形精灵来理解格式（注意grid中1和2对应palette[1]和palette[2]）：
[{"name":"爱心","grid":["0000000000000000","0000110000110000","0001221001221000","0012222101222100","0012222222222100","0001222222221000","0000122222210000","0000012222100000","0000001221000000","0000000110000000","0000000000000000","0000000000000000","0000000000000000","0000000000000000","0000000000000000","0000000000000000"],"palette":["transparent","#ff6b8a","#ff2d55"],"size":16,"cell_scale":2,"duration":3,"spread":0.7,"weight":0.7,"count":2}]

只输出JSON数组，不要其他内容。"""


def build_sprite_user_prompt(keywords: list[str]) -> str:
    """Build user message with keywords for sprite generation."""
    return f"生成像素精灵：{', '.join(keywords)}"
