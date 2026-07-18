"""心理健康辅助模块 — 危机检测 + 治疗意图分析 + 模块化干预框架.

三层危机检测 (crisis.py):
  1. 关键词启发式 (零 LLM 成本)
  2. LLM 复核 (仅在触发时)
  3. 上下文注入 (危机说话指南 + 热线号码)

治疗意图分析 (intent.py):
  独立轻量 prompt, 与现有 _INTENT_PROMPT 并行运行

模块化内容 (modules.py):
  venting / cbt / mindfulness / crisis 四个治疗模块桩
  Phase 1 为最小实现, Phase 2 将扩展完整内容
"""

from services.therapy.crisis import (
    crisis_keyword_check,
    crisis_llm_verify,
    get_crisis_context,
    log_crisis_event,
    update_risk_snapshot,
    get_risk_snapshot,
)
from services.therapy.intent import (
    analyze_therapy_intent,
    get_therapy_modules,
)
from services.therapy.modules import (
    assemble_therapy_modules,
)
from services.therapy.seed_data import (
    seed_crisis_resources,
)
