"""Style Distillation — analyze chat logs and mimic speaking styles.

Exports:
    analyze_style: Core analysis pipeline (parse + LLM extract).
    parse_chat_file: Multi-format chat log parser.
    DistilledProfile, StyleVector: Data models.
    list_profiles, save_profile, get_active_profile, delete_profile,
    activate_profile, deactivate_all: Profile CRUD and activation management.
"""

from services.distill.models import DistilledProfile, StyleVector
from services.distill.file_parser import parse_chat_file
from services.distill.analyzer import analyze_style
from services.distill.profile_store import (
    list_profiles,
    get_profile,
    save_profile,
    get_active_profile,
    delete_profile,
    activate_profile,
    deactivate_all,
)
