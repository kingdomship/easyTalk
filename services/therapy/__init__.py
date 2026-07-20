"""心理健康辅助模块 — 危机检测 + 治疗意图分析 + 情绪降级 + 模块化干预框架.

三层危机检测 (crisis.py):
  1. 关键词启发式 (零 LLM 成本)
  2. LLM 复核 (仅在触发时)
  3. 上下文注入 (危机说话指南 + 热线号码)

治疗意图分析 (intent.py):
  独立轻量 prompt, 与现有 _INTENT_PROMPT 并行运行

情绪降级 (deescalation.py):
  两层 LLM: Layer1 轻量分类器 + Layer2 主LLM引导注入

模块化内容 (modules.py):
  venting / cbt / mindfulness / crisis / deescalation 五个治疗模块
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
    assemble_deescalation_module,
)
from services.therapy.deescalation import (
    analyze_deescalation,
    analyze_deescalation_sync,
    get_deescalation_context,
)
from services.therapy.seed_data import (
    seed_crisis_resources,
)
