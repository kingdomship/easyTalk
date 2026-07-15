"""Mahalanobis-distance persona drift detector with multi-level intervention.

Replaces the simple LLM-based scoring in identity_guard.py with:

1. BASELINE: 50 compliant replies → hash-vector embeddings → Gaussian (mu, Sigma)
2. MAHALANOBIS DISTANCE: D_M(x) = sqrt(sum((x_i - mu_i)^2 / Sigma_ii))
   Captures directional deviation — "too cold" flagged more strongly than "too chatty"
3. WEIGHTED CORESET: 128-point decaying store for trend analysis
4. MULTI-LEVEL CLASSIFICATION:
   - Green  (D_M < 2.0): normal
   - Yellow (D_M < 3.0): log + observe
   - Orange (D_M < 4.0): inject reinforce prompt
   - Red    (D_M < 6.0): inject correct prompt
   - Black  (D_M >= 6.0): inject reset prompt
5. TREND PREDICTION: linear regression over 32 most recent coreset points
   → predicts turns until each threshold is crossed
"""

import json
import logging
import math
import os

from app.db import q, execute

logger = logging.getLogger("emoji-chat")

VEC_DIM = 256

# ── Thresholds ──────────────────────────────────────────────────────

class Level:
    GREEN  = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED    = "red"
    BLACK  = "black"

_THRESHOLDS = [
    (Level.GREEN,  2.0),
    (Level.YELLOW, 3.0),
    (Level.ORANGE, 4.0),
    (Level.RED,    6.0),
    (Level.BLACK,  float("inf")),
]

_INTERVENTIONS = {
    Level.GREEN:  "log",
    Level.YELLOW: "log",
    Level.ORANGE: "reinforce",
    Level.RED:    "correct",
    Level.BLACK:  "reset",
}

_CORESET_MAX = 128
_CORESET_DECAY = 0.995
_TREND_WINDOW = 32
_BASELINE_SAMPLES = 50


def _classify(distance: float) -> str:
    for level, threshold in _THRESHOLDS:
        if distance < threshold:
            return level
    return Level.BLACK


def _intervention_for(level: str) -> str:
    return _INTERVENTIONS.get(level, "log")


# ── Embedding helpers (reuse hash-vector scheme from memory_search) ──

def _text_to_embedding(text: str) -> list[float]:
    """Convert reply text to 256-dim vector using the hash-tag scheme.

    Zero external API cost — reuses the same scheme as memory_search.py.
    """
    import hashlib
    dim = VEC_DIM
    vec = [0.0] * dim
    # Use character trigrams as "tags" for the hash scheme
    text_bytes = text.encode("utf-8")
    for i in range(0, len(text_bytes) - 2, 3):
        trigram = text_bytes[i:i + 3]
        for seed in (0, 1, 2):
            h = hashlib.md5(trigram + bytes([seed]))
            pos = int.from_bytes(h.digest()[:2], "big") % dim
            val = (int.from_bytes(h.digest()[:1], "big") / 255.0) * 2 - 1
            vec[pos] += val
    norm = sum(v * v for v in vec) ** 0.5
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


# ── Baseline management ─────────────────────────────────────────────

def _build_baseline() -> dict | None:
    """Build the identity baseline from recent compliant replies.

    Selects the most recent chat_history replies, hashes them to vectors,
    computes mean and diagonal covariance.
    """
    rows = q(
        "SELECT avatar_reply FROM chat_history WHERE avatar_reply != '' "
        "ORDER BY id DESC LIMIT %s",
        [_BASELINE_SAMPLES * 2],  # fetch more than needed to allow filtering
    )
    if len(rows) < 10:
        logger.info("Not enough chat history for drift baseline (need >=10)")
        return None

    replies = [r["avatar_reply"] for r in rows if len(r["avatar_reply"]) > 5]
    if len(replies) < 10:
        return None
    replies = replies[:_BASELINE_SAMPLES]

    # Compute embeddings
    embeddings = [_text_to_embedding(r) for r in replies]
    n = len(embeddings)

    # Mean vector
    mean = [0.0] * VEC_DIM
    for emb in embeddings:
        for i in range(VEC_DIM):
            mean[i] += emb[i]
    mean = [m / n for m in mean]

    # Diagonal covariance
    cov_diag = [0.0] * VEC_DIM
    for emb in embeddings:
        for i in range(VEC_DIM):
            diff = emb[i] - mean[i]
            cov_diag[i] += diff * diff
    cov_diag = [max(1e-6, c / max(1, n - 1)) for c in cov_diag]  # avoid division by zero

    baseline = {
        "mean": mean,
        "cov_diag": cov_diag,
        "sample_count": n,
    }
    _store_baseline(baseline)
    logger.info("Drift baseline built: %d samples, dim=%d", n, VEC_DIM)
    return baseline


def _store_baseline(baseline: dict):
    """Persist baseline to drift_baseline table."""
    mean_json = json.dumps(baseline["mean"])
    cov_json = json.dumps(baseline["cov_diag"])
    execute(
        "INSERT INTO drift_baseline (mean_embedding, covariance_diag, sample_count) "
        "VALUES (%s::halfvec, %s::halfvec, %s)",
        [mean_json, cov_json, baseline["sample_count"]],
    )


def _load_baseline() -> dict | None:
    """Load the most recent baseline from DB."""
    row = q(
        "SELECT mean_embedding, covariance_diag, sample_count "
        "FROM drift_baseline ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if not row:
        return None
    # pgvector returns halfvec as a list-like in psycopg2
    # We need to handle both list and string representations
    mean = row["mean_embedding"]
    cov = row["covariance_diag"]
    if isinstance(mean, str):
        mean = json.loads(mean)
    if isinstance(cov, str):
        cov = json.loads(cov)
    # Ensure they're proper lists of floats
    mean = [float(x) for x in mean] if mean else []
    cov = [float(x) for x in cov] if cov else []
    if not mean or not cov:
        return None
    return {
        "mean": mean,
        "cov_diag": cov,
        "sample_count": row["sample_count"],
    }


def ensure_baseline() -> dict | None:
    """Get or build the drift baseline."""
    baseline = _load_baseline()
    if baseline is None:
        baseline = _build_baseline()
    return baseline


# ── Mahalanobis distance ─────────────────────────────────────────────

def mahalanobis_distance(embedding: list[float], baseline: dict) -> float:
    """Compute Mahalanobis distance: D_M(x) = sqrt(sum((x_i - mu_i)^2 / sigma_ii)).

    Uses diagonal covariance for efficiency. Captures directional deviation —
    sensitive dimensions (narrower variance) get higher weight.
    """
    mean = baseline["mean"]
    cov_diag = baseline["cov_diag"]
    if len(embedding) != len(mean):
        return 0.0

    total = 0.0
    for i in range(len(mean)):
        diff = embedding[i] - mean[i]
        total += (diff * diff) / cov_diag[i]
    return math.sqrt(total)


# ── Weighted coreset ─────────────────────────────────────────────────

def _add_to_coreset(reply_text: str, embedding: list[float], distance: float):
    """Add a point to the weighted coreset, evicting lowest-weight if full."""
    e_json = json.dumps(embedding)
    execute(
        "INSERT INTO drift_coreset (reply_text, embedding, weight, distance) "
        "VALUES (%s, %s::halfvec, 1.0, %s)",
        [reply_text[:200], e_json, round(distance, 4)],
    )

    # Decay all weights
    execute(
        f"UPDATE drift_coreset SET weight = weight * {_CORESET_DECAY}"
    )

    # Evict excess
    count_row = q("SELECT COUNT(*) AS cnt FROM drift_coreset", fetch="one")
    if count_row and count_row["cnt"] > _CORESET_MAX:
        execute(
            "DELETE FROM drift_coreset WHERE id = ("
            "SELECT id FROM drift_coreset ORDER BY weight ASC LIMIT 1"
            ")"
        )


def _get_coreset_distances() -> list[float]:
    """Get recent distances for trend analysis."""
    rows = q(
        "SELECT distance FROM drift_coreset ORDER BY id DESC LIMIT %s",
        [_TREND_WINDOW],
    )
    return [r["distance"] for r in rows]


# ── Trend prediction ─────────────────────────────────────────────────

def _predict_trend(distances: list[float]) -> dict:
    """Simple linear regression over recent distances.

    Returns {predicted_distance, turns_until_yellow, turns_until_orange, turns_until_red}.
    """
    n = len(distances)
    if n < 4:
        return {"predicted_distance": distances[-1] if distances else 0,
                "turns_until_yellow": None, "turns_until_orange": None,
                "turns_until_red": None}

    # Linear regression: distance = slope * turn_index + intercept
    xs = list(range(n))  # 0 = oldest, n-1 = newest
    ys = distances[::-1]  # reverse so oldest first

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((x - mean_x) ** 2 for x in xs)

    slope = num / den if den != 0 else 0
    intercept = mean_y - slope * mean_x

    # Predict distance in 5 turns
    predicted = slope * (n + 5 - 1) + intercept
    predicted = max(0, predicted)

    # Turns until each threshold
    def turns_until(threshold):
        if slope <= 0:
            return float("inf") if distances[-1] < threshold else 0
        return max(0, (threshold - distances[-1]) / slope)

    return {
        "predicted_distance": round(predicted, 3),
        "turns_until_yellow": round(turns_until(3.0), 1),
        "turns_until_orange": round(turns_until(4.0), 1),
        "turns_until_red": round(turns_until(6.0), 1),
    }


# ── Intervention prompts ─────────────────────────────────────────────

_REINFORCE_PROMPT = """⚠️ **人设提醒**：你最近的表达风格有轻微偏离，请在接下来的回复中 **reinforce** 你的核心人格特质 —— 回想你最初的样子，回归那个温暖俏皮的自己。"""

_CORRECT_PROMPT = """⚠️ **人设修正**：你最近的回复明显偏离了你的核心人格。请立即调整：
- 重新读一遍你的人设描述
- 检查上一条回复中哪些表达不符合你的性格
- 在接下来的回复中回归你的人设，像一个"重新校准"的过程"""

_RESET_PROMPT = """⛔ **人设重置**：你最近的表达已经严重偏离了你的角色定义。请在回复前：
1. 深呼吸，重新确认"我是谁"
2. 完全忽略上几条回复的风格
3. 像一个刚被唤醒的角色一样，用你最本质的声音回应"""


def get_level_correction(level: str) -> str:
    """Return the appropriate correction prompt for a drift level."""
    if level == Level.GREEN:
        return ""
    elif level == Level.YELLOW:
        return ""
    elif level == Level.ORANGE:
        return _REINFORCE_PROMPT
    elif level == Level.RED:
        return _CORRECT_PROMPT
    elif level == Level.BLACK:
        return _RESET_PROMPT
    return ""


# ── Main check ───────────────────────────────────────────────────────

def check_and_intervene(reply_text: str) -> str:
    """Evaluate a reply for persona drift and return intervention level.

    Called after each AI reply is generated. Returns the level string
    for logging and potential context injection.
    """
    baseline = ensure_baseline()
    if not baseline:
        return Level.GREEN

    embedding = _text_to_embedding(reply_text)
    distance = mahalanobis_distance(embedding, baseline)

    _add_to_coreset(reply_text, embedding, distance)

    level = _classify(distance)
    intervention = _intervention_for(level)

    # Trend prediction
    distances = _get_coreset_distances()
    trend = _predict_trend(distances)

    # Log if above green
    if level != Level.GREEN:
        details = json.dumps({
            "distance": round(distance, 4),
            "predicted": trend["predicted_distance"],
            "turns_to_yellow": trend["turns_until_yellow"],
            "turns_to_orange": trend["turns_until_orange"],
            "turns_to_red": trend["turns_until_red"],
        })
        execute(
            "INSERT INTO drift_log (level, mahalanobis_distance, predicted_distance, "
            "turns_until_threshold, intervention, details) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [level, round(distance, 4), trend["predicted_distance"],
             trend["turns_until_yellow"], intervention, details],
        )
        logger.warning(
            "Drift: level=%s distance=%.3f predicted=%.3f intervention=%s",
            level, distance, trend["predicted_distance"], intervention,
        )

    return level


def get_drift_correction() -> str:
    """Return the appropriate correction prompt for the most recent drift.

    Called during _build_context() to inject intervention into system prompt.
    """
    row = q(
        "SELECT level, mahalanobis_distance FROM drift_log "
        "ORDER BY id DESC LIMIT 1",
        fetch="one",
    )
    if not row:
        return ""
    level = row["level"]
    return get_level_correction(level)
