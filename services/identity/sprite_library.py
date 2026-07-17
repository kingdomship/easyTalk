"""Pixel sprite library — loads 16×16 sprites from JSON, upscales to 48×48.

Sprites are stored as 16×16 grids in services/identity/sprites/ (one JSON file
per category). LLM generation at 16×16 is reliable; 48×48 grids produced by
the LLM are mostly blank. The library transparently upscales 16→48 via
nearest-neighbour so the frontend receives high-resolution 48×48 sprites.

LLM-generated sprites are persisted to _generated.json for future reuse.
"""

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

STORED_SIZE = 16    # grid size stored in JSON (LLM-friendly)
SERVED_SIZE = 48    # grid size served to frontend
UPSCALE_FACTOR = SERVED_SIZE // STORED_SIZE  # 3x

# ── Paths ─────────────────────────────────────────────────────────

_SPRITE_DIR = os.path.join(os.path.dirname(__file__), "sprites")
_GENERATED_FILE = os.path.join(_SPRITE_DIR, "_generated.json")
_GENERATED_LOCK = threading.Lock()

# ── In-memory library ─────────────────────────────────────────────

SPRITE_LIBRARY: dict[str, dict] = {}


# ── Grid operations ────────────────────────────────────────────────

def _count_pixels(grid: list[str]) -> int:
    return sum(1 for row in grid for c in row if c != "0")


def _upscale_grid(grid: list[str]) -> list[str]:
    """Upscale a 16×16 grid to 48×48 via nearest-neighbour (3x pixel doubling).

    Each pixel becomes a 3×3 block, preserving the pixel-art aesthetic.
    If the grid is already 48×48 it is returned unchanged.
    """
    if not grid:
        return grid
    if len(grid) == SERVED_SIZE and len(grid[0]) == SERVED_SIZE:
        return grid
    result = []
    for row in grid:
        expanded_row = "".join(c * UPSCALE_FACTOR for c in row)
        for _ in range(UPSCALE_FACTOR):
            result.append(expanded_row)
    return result


# ── Validation ────────────────────────────────────────────────────

def _validate_sprite(sprite: dict) -> bool:
    """Validate a sprite dict. Accepts both 16×16 and 48×48 grids."""
    if not isinstance(sprite.get("name"), str) or not sprite["name"]:
        return False

    keywords = sprite.get("keywords", [])
    if not isinstance(keywords, list) or len(keywords) < 1:
        return False

    grid = sprite.get("grid")
    if not isinstance(grid, list):
        return False
    grid_size = len(grid)
    if grid_size not in (STORED_SIZE, SERVED_SIZE):
        return False

    pixels = 0
    for row in grid:
        if not isinstance(row, str) or len(row) != grid_size:
            return False
        if not all(c in "0123456789" for c in row):
            return False
        pixels += _count_pixels([row])
    if pixels < 5:
        return False

    palette = sprite.get("palette", [])
    if not isinstance(palette, list) or len(palette) < 2:
        return False
    if palette[0] != "transparent":
        return False

    return True


# ── Loading ───────────────────────────────────────────────────────

def _load_sprite_json() -> int:
    """Load all sprite JSON files into SPRITE_LIBRARY.

    Grids are stored at 16×16; they are upscaled to 48×48 on lookup.
    Returns the number of sprites loaded.
    """
    if not os.path.isdir(_SPRITE_DIR):
        logger.warning("Sprite directory not found: %s", _SPRITE_DIR)
        return 0

    total = 0
    files_loaded = 0
    for fname in sorted(os.listdir(_SPRITE_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(_SPRITE_DIR, fname)
        try:
            with open(path, encoding="utf-8") as f:
                sprites = json.load(f)
        except Exception as exc:
            logger.error("Failed to load sprite file %s: %s", fname, exc)
            continue

        if not isinstance(sprites, list):
            logger.warning("Sprite file %s is not a JSON array, skipping", fname)
            continue

        file_count = 0
        for sprite in sprites:
            if not _validate_sprite(sprite):
                logger.warning("Invalid sprite '%s' in %s, skipping",
                               sprite.get("name", "?"), fname)
                continue
            keywords = sprite.pop("keywords", [])
            # Store at 16×16; upscale happens in _build_result
            for kw in keywords:
                SPRITE_LIBRARY[kw] = sprite
            file_count += 1

        total += file_count
        files_loaded += 1
        logger.info("Loaded %d sprites from %s", file_count, fname)

    logger.info("Sprite library: %d sprites / %d keywords from %d files",
                total, len(SPRITE_LIBRARY), files_loaded)
    return total


# ── Persistence ───────────────────────────────────────────────────

def persist_sprite(sprite: dict, keywords: list[str]) -> bool:
    """Save a newly generated sprite to _generated.json for future reuse.

    Accepts either 16×16 or 48×48 grids; stores at 16×16.
    Also registers it in the in-memory SPRITE_LIBRARY immediately.
    Thread-safe via _GENERATED_LOCK.
    """
    if not keywords:
        return False

    grid = sprite.get("grid", [])
    # If LLM happened to return 48×48, downsample to 16×16 for storage
    if len(grid) == SERVED_SIZE:
        grid = [row[::UPSCALE_FACTOR] for row in grid[::UPSCALE_FACTOR]]

    entry = {
        "name": sprite.get("name", keywords[0]),
        "keywords": list(keywords),
        "grid": grid,
        "palette": sprite["palette"],
        "cell_scale": sprite.get("cell_scale", 2.0),
        "duration": sprite.get("duration", 3),
        "spread": sprite.get("spread", 0.7),
        "weight": sprite.get("weight", 0.5),
        "count": sprite.get("count", 2),
    }
    if sprite.get("size"):
        entry["size"] = sprite["size"]
    if sprite.get("anchor"):
        entry["anchor"] = sprite["anchor"]
        entry["anchor_rx"] = sprite.get("anchor_rx", 0)
        entry["anchor_ry"] = sprite.get("anchor_ry", -18)

    if not _validate_sprite(entry):
        logger.warning("persist_sprite: validation failed for '%s'", entry.get("name"))
        return False

    # Register in-memory immediately
    for kw in keywords:
        SPRITE_LIBRARY[kw] = entry

    # Persist to disk
    with _GENERATED_LOCK:
        existing: list = []
        if os.path.exists(_GENERATED_FILE):
            try:
                with open(_GENERATED_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        names = {s.get("name") for s in existing}
        if entry["name"] in names:
            return True

        existing.append(entry)
        try:
            os.makedirs(_SPRITE_DIR, exist_ok=True)
            with open(_GENERATED_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
            logger.info("Persisted sprite '%s' to _generated.json", entry["name"])
        except Exception as exc:
            logger.error("Failed to persist sprite '%s': %s", entry["name"], exc)
            return False

    return True


# ── Lookup ────────────────────────────────────────────────────────

def _fuzzy_match(keywords: list[str]) -> tuple[str, dict] | None:
    """Try to match keywords against the library with substring matching.

    Two-tier fallback after exact match fails:
    1. Keyword contains a library key (e.g. "橘猫" contains "猫")
    2. Library key contains a keyword (e.g. keyword "猫" matches "猫咪")

    Returns (matched_keyword, sprite_entry) or None.
    Prefers longer matches to reduce false positives.
    """
    if not keywords:
        return None

    candidates: list[tuple[int, str, dict]] = []

    for kw in keywords:
        for lib_kw, entry in SPRITE_LIBRARY.items():
            if lib_kw in kw and lib_kw != kw:
                candidates.append((len(lib_kw) * 10, lib_kw, entry))
            if kw in lib_kw and kw != lib_kw:
                candidates.append((len(kw) * 5, lib_kw, entry))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, matched_kw, entry = candidates[0]
    return matched_kw, entry


def lookup_sprite(keywords: list[str]) -> dict | None:
    """Check if any keyword matches a library sprite.

    Three-tier lookup:
    1. Exact keyword match (O(1) dict lookup)
    2. Fuzzy: keyword contains library key (e.g. "橘猫" → "猫")
    3. Fuzzy: library key contains keyword (e.g. "猫" → "猫咪")

    Returns a ready-to-use sprite dict with **48×48 upscaled grid**, or None.
    """
    if not keywords:
        return None

    for kw in keywords:
        entry = SPRITE_LIBRARY.get(kw)
        if entry:
            return _build_result(entry, kw)

    fuzzy = _fuzzy_match(keywords)
    if fuzzy:
        matched_kw, entry = fuzzy
        logger.info("Fuzzy sprite match: keywords=%s → '%s'", keywords, matched_kw)
        return _build_result(entry, matched_kw)

    return None


def _build_result(entry: dict, kw: str) -> dict:
    """Build a ready-to-use sprite dict, upscaling grid from 16×16 to 48×48."""
    result = {
        "grid": _upscale_grid(entry["grid"]),
        "palette": list(entry["palette"]),
        "count": entry.get("count", 2),
        "spread": entry.get("spread", 0.7),
        "weight": entry.get("weight", 0.5),
        "duration": entry.get("duration", 3),
        "cell_scale": entry.get("cell_scale", 2.0),
        "name": kw,
        "size": SERVED_SIZE,
    }
    if entry.get("anchor"):
        result["anchor"] = entry["anchor"]
        result["anchor_rx"] = entry.get("anchor_rx", 0)
        result["anchor_ry"] = entry.get("anchor_ry", -18)
    return result


def get_library_keywords() -> list[str]:
    """Return all known keywords (for debugging)."""
    return list(SPRITE_LIBRARY.keys())


# ── Load on import ────────────────────────────────────────────────

_load_sprite_json()
