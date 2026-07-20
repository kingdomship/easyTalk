"""Data models for distilled conversation styles."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class StyleVector:
    """8-dimension continuous style vector representing a distilled persona."""

    formality: float = 0.5
    warmth: float = 0.5
    humor: float = 0.5
    verbosity: float = 0.5
    figurative: float = 0.5
    emotionality: float = 0.5
    directness: float = 0.5
    empathy: float = 0.5

    def to_prompt_segment(self) -> str:
        """Convert vector to natural-language description for prompt injection."""
        lines = []

        if self.formality <= 0.3:
            lines.append("- 说话非常随意自然，像朋友间聊天，不讲究措辞")
        elif self.formality >= 0.7:
            lines.append("- 说话得体考究，用词规范，有一定正式感")
        elif self.formality <= 0.45:
            lines.append("- 偏随意，不太讲究书面语")

        if self.warmth >= 0.7:
            lines.append("- 语气温暖亲切，让人感到被关心")
        elif self.warmth <= 0.3:
            lines.append("- 语气平和冷静，保持一定距离感")

        if self.humor >= 0.65:
            lines.append("- 喜欢用幽默和俏皮话调节气氛")
        elif self.humor <= 0.35:
            lines.append("- 说话认真诚恳，不刻意搞笑")

        if self.verbosity >= 0.7:
            lines.append("- 说话比较啰嗦，喜欢展开说明细节")
        elif self.verbosity <= 0.3:
            lines.append("- 说话简洁直接，不拖泥带水")

        if self.figurative >= 0.65:
            lines.append("- 善用比喻和联想，表达偏抽象形象")
        elif self.figurative <= 0.35:
            lines.append("- 表达直白具体，不绕弯子")

        if self.emotionality >= 0.7:
            lines.append("- 情绪表达丰富外放，喜怒哀乐溢于言表")
        elif self.emotionality <= 0.3:
            lines.append("- 情绪表达克制内敛，不轻易表露内心波动")

        if self.directness >= 0.7:
            lines.append("- 说话直截了当，不绕弯子")
        elif self.directness <= 0.3:
            lines.append("- 说话委婉含蓄，喜欢铺垫")

        if self.empathy >= 0.7:
            lines.append("- 习惯先共情理解再回应，让对方感到被倾听")
        elif self.empathy <= 0.3:
            lines.append("- 偏理性分析，不轻易表达共情")

        if not lines:
            lines.append("- 整体风格中性自然，没有特别明显的特征")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> StyleVector:
        defaults = asdict(cls())
        for k, v in d.items():
            if k in defaults:
                defaults[k] = v
        return cls(**defaults)


@dataclass
class DistilledProfile:
    """Complete distilled style profile."""

    id: str
    name: str
    source: str  # "txt" | "json"
    created_at: str  # ISO datetime
    updated_at: str  # ISO datetime
    sample_count: int = 0
    style_vector: StyleVector = field(default_factory=StyleVector)
    linguistic_markers: list[str] = field(default_factory=list)
    vocabulary: list[str] = field(default_factory=list)
    sample_sentences: list[str] = field(default_factory=list)
    raw_analysis: str = ""
    active: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["style_vector"] = self.style_vector.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DistilledProfile:
        sv_data = d.get("style_vector", {})
        sv = StyleVector.from_dict(sv_data) if sv_data else StyleVector()
        # Shallow copy to avoid mutating the caller's dict
        rest = {k: v for k, v in d.items() if k != "style_vector"}
        return cls(style_vector=sv, **rest)
