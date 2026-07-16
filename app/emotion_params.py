"""Canonical emotion parameter definitions — single source of truth.

Every parameter spec: (default, min_val, max_val, jitter_amount)
Adding a new param here automatically propagates to:
  - _default_frame / _clamp / _jitter_frame in chat.py
  - _upsert SQL generation
  - _row_to_response DB row conversion
  - NEUTRAL_PARAMS for expression amplitude scaling
"""

from collections import OrderedDict

# Ordered to match DB column order in emotion_cache table
EMOTION_PARAMS: OrderedDict[str, tuple[float, float, float, float]] = OrderedDict([
    # (name,           default, min,  max, jitter)
    ("eye_curve",       (0.0,   -1.0,  1.0, 0.03)),
    ("eye_open",        (0.5,    0.0,  1.0, 0.02)),
    ("eye_pupil",       (0.0,   -1.0,  1.0, 0.02)),
    ("eye_wink",        (0.0,   -1.0,  1.0, 0.01)),
    ("eye_tension",     (0.0,    0.0,  1.0, 0.01)),
    ("iris_size",       (0.5,    0.0,  1.0, 0.015)),
    ("mouth_curve",     (0.0,   -1.0,  1.0, 0.03)),
    ("mouth_open",      (0.0,    0.0,  1.0, 0.02)),
    ("mouth_width",     (0.8,    0.3,  1.0, 0.015)),
    ("mouth_asym",      (0.0,   -1.0,  1.0, 0.01)),
    ("lip_pout",        (0.0,    0.0,  1.0, 0.01)),
    ("lip_stretch",     (0.0,    0.0,  1.0, 0.01)),
    ("lip_bite",        (0.0,    0.0,  1.0, 0.01)),
    ("jaw_drop",        (0.0,    0.0,  1.0, 0.01)),
    ("tongue_out",      (0.0,    0.0,  1.0, 0.005)),
    ("sparkle",         (0.5,    0.0,  1.0, 0.02)),
    ("brow_angle",      (0.0,   -1.0,  1.0, 0.03)),
    ("brow_height",     (0.5,    0.0,  1.0, 0.02)),
    ("brow_asym",       (0.0,    0.0,  1.0, 0.015)),
    ("nose_wrinkle",    (0.0,    0.0,  1.0, 0.01)),
    ("cheek_raise",     (0.0,    0.0,  1.0, 0.015)),
    ("cheek_puff",      (0.0,    0.0,  1.0, 0.01)),
    ("blush",           (0.0,    0.0,  1.0, 0.015)),
    ("head_tilt",       (0.0,   -1.0,  1.0, 0.015)),
    ("tear",            (0.0,    0.0,  1.0, 0.01)),
    ("sweat_drop",      (0.0,    0.0,  1.0, 0.01)),
    ("vein_pop",        (0.0,    0.0,  1.0, 0.005)),
])

_PARAM_NAMES = list(EMOTION_PARAMS.keys())
PARAM_DEFAULTS: dict[str, float] = {name: spec[0] for name, spec in EMOTION_PARAMS.items()}


def make_default_frame(label: str = "neutral", duration_ms: int = 3000) -> dict:
    """Build a neutral frame with all canonical defaults."""
    frame: dict = {"label": label, "duration_ms": duration_ms}
    frame.update(PARAM_DEFAULTS)
    return frame


def clamp_frame(frame: dict) -> dict:
    """Clamp all emotion params to valid ranges."""
    result = {
        "label": str(frame.get("label", "unknown"))[:30],
        "duration_ms": max(500, min(10000, int(frame.get("duration_ms", 3000)))),
    }
    for name, (default, lo, hi, _jitter) in EMOTION_PARAMS.items():
        result[name] = max(lo, min(hi, float(frame.get(name, default))))
    return result


def jitter_frame(frame: dict) -> dict:
    """Apply random micro-jitter to a frame for liveliness."""
    import random
    result = dict(frame)
    for name, (default, lo, hi, amount) in EMOTION_PARAMS.items():
        val = result.get(name, default) + (random.random() * 2 - 1) * amount
        result[name] = max(lo, min(hi, val))
    return result


def frame_to_db_values(frame: dict) -> list[float]:
    """Extract emotion param values in DB column order."""
    return [frame.get(name, PARAM_DEFAULTS[name]) for name in _PARAM_NAMES]


def row_to_frame_dict(row: dict) -> dict[str, float]:
    """Extract emotion params from a DB row dict."""
    return {name: row.get(name, PARAM_DEFAULTS[name]) for name in _PARAM_NAMES}
