"""Emotion & relationship system — affect, affinity, attachment, and salience."""

from services.emotion.affect import (
    init_affect_db, get_affect, assess_affect, update_affect,
    dominant_affect, get_regulation_strategy, get_affect_context,
    snapshot_for_valence, get_valence_context,
)
from services.emotion.affinity import (
    init_affinity_db, get_affinity, update_affinity, get_affinity_context,
    get_expression_amplitude, adjust_expression_amplitude, scale_emotion_params,
    check_milestones, get_milestones,
)
from services.emotion.attachment import analyze_attachment, get_attachment_context
from services.emotion.salience import init_salience_db, get_salience, update_salience, get_salience_context
