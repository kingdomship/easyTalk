"""Centralized path configuration for easyTalk."""

import os
import threading

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
APIKEY_PATH = os.path.join(MEMORY_DIR, "api_key.txt")

LIFE_DOMAINS_PATH = os.path.join(MEMORY_DIR, "life_domains.json")
CURIOSITY_PATH = os.path.join(MEMORY_DIR, "curiosity_queue.json")

LOG_DIR = os.path.join(MEMORY_DIR, "logs")

METAPHYSICS_DIR = os.path.join(MEMORY_DIR, "metaphysics")
BIRTH_INFO_PATH = os.path.join(METAPHYSICS_DIR, "birth_info.json")
BAZI_CACHE_PATH = os.path.join(METAPHYSICS_DIR, "bazi_cache.json")
ZIWEI_CACHE_PATH = os.path.join(METAPHYSICS_DIR, "ziwei_cache.json")
CHART_CACHE_PATH = os.path.join(METAPHYSICS_DIR, "chart_cache.json")

# Lock for thread-safe archive file access
archive_lock = threading.Lock()


def atomic_write(path: str, data: str):
    """Write data to a file atomically via temp file + rename.

    Ensures data is flushed to disk before the atomic rename, preventing
    partial writes from surviving a crash.
    """
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
