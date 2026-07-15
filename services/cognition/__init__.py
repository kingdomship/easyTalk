"""Cognitive engine — state machine, prediction, and dual-system reasoning."""

from services.cognition.state_machine import (
    determine_mode, get_mode_suffix, get_mode_temp_mod,
    determine_arousal, get_arousal_temp_mod, get_arousal_token_mod,
    get_arousal_amplitude_mod,
)
from services.cognition.prediction import generate_prediction, check_prediction, get_prediction_context
from services.cognition.predictive_agent import (
    pre_dialogue_analyze, preload_memories, feedback,
    get_prediction_context as agent_prediction_context,
    offline_analysis,
)
from services.cognition.dual_system import (
    gate_decision, detect_contradictions, assess_impact,
    store_insight, system2_consolidation,
)
