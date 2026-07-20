"""接纳承诺疗法 (ACT) — 认知解离 + 价值观澄清.

认知解离: 纯提示词注入, 零额外 LLM 成本
价值观澄清: 引导对话 + 持久化到 user_values.json
"""

import json
import os
import threading
from app.config import USER_VALUES_PATH

_act_lock = threading.Lock()

# ── 价值观澄清引导问题 ──────────────────────────────────────

VALUES_QUESTIONS = [
    "请完成这个句子：对我来说重要的三个方面是______、______和______。",
    "如果你有魔法可以改变生活的一个方面，那会是什么？",
    "什么让你感到充满活力？什么消耗你？",
    "回想一个让你感到骄傲的时刻——那时你在做什么？",
    "如果你的生活是一本书，你希望下一章的标题是什么？",
]


def load_user_values() -> dict | None:
    """读取用户价值观档案."""
    try:
        if not os.path.exists(USER_VALUES_PATH):
            return None
        with _act_lock:
            with open(USER_VALUES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return None


def save_user_values(values: dict) -> None:
    """原子写入用户价值观档案."""
    try:
        tmp_path = USER_VALUES_PATH + ".tmp"
        with _act_lock:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(values, f, ensure_ascii=False, indent=2)
            os.rename(tmp_path, USER_VALUES_PATH)
    except Exception:
        pass


def get_act_defusion_guide() -> str:
    """返回认知解离引导文本 (纯提示词, 无 LLM 调用)."""
    return """## 认知解离 (ACT)

用户可能陷入了与负面想法的"融合"——把想法当作事实。请帮助用户拉开与想法的距离：

### 解离技术
1. **标签式重述**: "我注意到你对自己说 '[原文]'" — 创造观察者与内容之间的距离
2. **为想法命名**: "如果给这个想法取个名字, 你会叫它什么？'我做不到'先生又来了？"
3. **感谢大脑**: "谢谢大脑提供这个想法, 不过我现在不需要它"
4. **用不同声音默念**: 邀请用户在心里用搞笑的卡通声音复述那个自我批评的念头
5. **外部化**: "把这个想法想象成收音机里的一个频道, 你可以选择不收听"

### 核心原则
- 不挑战想法是否"正确" — 改变与想法的关系, 而非内容
- 解离不是消除 — 想法还在, 但它对你的控制力减弱了
- 用故事和比喻, 不说教"""


def get_act_values_context() -> str:
    """返回价值观澄清引导上下文, 含已有价值观引用."""
    values = load_user_values()
    if not values or not values.get("values"):
        return ""

    parts = ["## 用户价值观 (ACT)", "已知用户珍视的方面："]
    for v in values.get("values", []):
        parts.append(f"- {v}")
    parts.append("在合适的时候，可以温和地帮用户把当前困扰和ta的价值观联系起来。")
    parts.append("例如: '你之前说过{value}对你很重要, 现在的选择是否与它一致？'")
    return "\n".join(parts)


def get_act_context() -> str:
    """返回完整的 ACT 上下文 (解离指导 + 价值观引用)."""
    parts = [get_act_defusion_guide()]
    values_ctx = get_act_values_context()
    if values_ctx:
        parts.append(values_ctx)
    return "\n\n".join(parts)
