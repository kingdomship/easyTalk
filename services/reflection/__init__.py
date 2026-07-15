"""Reflection system — consciousness loop, idle thoughts, and diary generation."""

from services.reflection.consciousness_loop import (
    init_loop_db, idle_thought, mood_fluctuation, diary_seed,
    system2_consolidation, get_latest_idle_thought,
)
from services.reflection.diary import generate_diary, get_diaries, get_diary
