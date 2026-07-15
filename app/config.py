"""Centralized path configuration for easyTalk."""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_DIR = os.environ.get("MEMORY_DIR", os.path.join(BASE_DIR, "memory"))

ARCHIVE_PATH = os.path.join(MEMORY_DIR, "conversation_archive.jsonl")
SUMMARY_PATH = os.path.join(MEMORY_DIR, "conversation_summary.md")
PROFILE_PATH = os.path.join(MEMORY_DIR, "user_profile.md")
PERSONA_PATH = os.path.join(MEMORY_DIR, "user_persona.md")
CRYSTAL_PATH = os.path.join(MEMORY_DIR, "crystals.jsonl")
SITUATIONS_PATH = os.path.join(MEMORY_DIR, "situations.jsonl")
EPISODES_PATH = os.path.join(MEMORY_DIR, "episodes.jsonl")
MILESTONE_PATH = os.path.join(MEMORY_DIR, "milestones.jsonl")
STYLE_PATH = os.path.join(MEMORY_DIR, "attachment_style.json")
DRIFT_LOG_PATH = os.path.join(MEMORY_DIR, "drift_log.jsonl")
PREDICTION_PATH = os.path.join(MEMORY_DIR, "prediction.json")
SALIENCE_PREV_PATH = os.path.join(MEMORY_DIR, "salience_prev.json")
VALENCE_PREV_PATH = os.path.join(MEMORY_DIR, "valence_prev.json")
PERSONALITY_CONFIG_PATH = os.path.join(MEMORY_DIR, "personality_config.json")
