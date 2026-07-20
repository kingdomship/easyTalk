"""Persist and manage distilled style profiles as JSON files.

Each profile is stored as a separate JSON file in DISTILL_DIR.
Only one profile can be active at a time.
"""

import json
import os
import re
import logging
from typing import Optional

from app.config import DISTILL_DIR
from services.distill.models import DistilledProfile

logger = logging.getLogger("emoji-chat")

# profile_id only allows hex chars (UUID prefix), max 64 chars
_ID_PATTERN = re.compile(r"^[a-f0-9]{1,64}$")


def _validate_profile_id(profile_id: str) -> bool:
    return bool(_ID_PATTERN.match(profile_id))


def _ensure_dir():
    """Ensure the distill directory exists."""
    os.makedirs(DISTILL_DIR, exist_ok=True)


def _profile_path(profile_id: str) -> str:
    """Return the full path for a profile JSON file (with path-traversal guard)."""
    if not _validate_profile_id(profile_id):
        raise ValueError(f"Invalid profile_id: {profile_id}")
    return os.path.join(DISTILL_DIR, f"{profile_id}.json")


def list_profiles() -> list[DistilledProfile]:
    """Return all saved profiles, newest first."""
    _ensure_dir()
    profiles = []
    try:
        for fname in os.listdir(DISTILL_DIR):
            if not fname.endswith(".json"):
                continue
            filepath = os.path.join(DISTILL_DIR, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                profiles.append(DistilledProfile.from_dict(data))
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning("Skipping corrupt profile file %s: %s", fname, e)
    except OSError as e:
        logger.error("Failed to list profiles: %s", e)
    profiles.sort(key=lambda p: p.created_at, reverse=True)
    return profiles


def get_profile(profile_id: str) -> Optional[DistilledProfile]:
    """Get a single profile by ID."""
    path = _profile_path(profile_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DistilledProfile.from_dict(data)
    except Exception:
        logger.warning("Failed to read profile %s", profile_id, exc_info=True)
        return None


def save_profile(profile: DistilledProfile):
    """Save or update a profile. Caller is responsible for activation logic."""
    _ensure_dir()
    _save_one(profile)


def _save_one(profile: DistilledProfile):
    """Write a single profile to disk."""
    path = _profile_path(profile.id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("Failed to save profile %s: %s", profile.id, e)
        raise


def get_active_profile() -> Optional[DistilledProfile]:
    """Return the currently active distilled profile, or None."""
    for p in list_profiles():
        if p.active:
            return p
    return None


def delete_profile(profile_id: str) -> bool:
    """Delete a profile by ID. Returns True if deleted, False if not found."""
    path = _profile_path(profile_id)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError as e:
            logger.error("Failed to delete profile %s: %s", profile_id, e)
    return False


def activate_profile(profile_id: str) -> Optional[DistilledProfile]:
    """Activate a profile and deactivate all others. Returns the activated profile."""
    _ensure_dir()
    profiles = list_profiles()
    target = None
    for p in profiles:
        should_be_active = p.id == profile_id
        if should_be_active:
            target = p
        if p.active != should_be_active:
            p.active = should_be_active
            _save_one(p)
    return target


def deactivate_all():
    """Deactivate all profiles, returning to default AI style."""
    _ensure_dir()
    for p in list_profiles():
        if p.active:
            p.active = False
            _save_one(p)

