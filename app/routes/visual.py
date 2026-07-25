"""Visual perception endpoints — camera frame upload, analysis, preview."""

import base64
import logging
import time
import threading
from collections import deque
from io import BytesIO

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app.utils import get_visual_llm, stitch_frames, analyze_frames
from app.audit import audit_log

router = APIRouter()
logger = logging.getLogger("emoji-chat")

# ── Ring buffer: per-session frame storage ─────────────────────────
# Single-user app, but keyed by session_id for future extensibility.
# Each frame: {"timestamp": float, "image_base64": str, "index": int}
_MAX_FRAMES = 20
_frame_buffers: dict[str, deque] = {}
_buf_lock = threading.Lock()
_frame_index: dict[str, int] = {}


def _get_buffer(session_id: str = "default") -> deque:
    with _buf_lock:
        if session_id not in _frame_buffers:
            _frame_buffers[session_id] = deque(maxlen=_MAX_FRAMES)
            _frame_index[session_id] = 0
        return _frame_buffers[session_id]


# ── Pydantic models ───────────────────────────────────────────────

class UploadFrameRequest(BaseModel):
    image_base64: str
    session_id: str = "default"

    @field_validator("image_base64")
    @classmethod
    def check_size(cls, v: str) -> str:
        if len(v) > 200_000:  # 200KB max
            raise ValueError("Frame too large")
        return v


class AnalyzeRequest(BaseModel):
    query: str
    session_id: str = "default"


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/api/visual/upload")
async def upload_frame(data: UploadFrameRequest):
    """Receive a single camera frame (base64 JPEG) and store in ring buffer."""
    try:
        buf = _get_buffer(data.session_id)
        with _buf_lock:
            idx = _frame_index.get(data.session_id, 0)
            _frame_index[data.session_id] = idx + 1

        # Decode + re-encode to 320×240 for storage efficiency
        try:
            from PIL import Image
            raw = base64.b64decode(data.image_base64)
            img = Image.open(BytesIO(raw)).resize((320, 240), Image.LANCZOS)
            out = BytesIO()
            img.save(out, format="JPEG", quality=60)
            compressed = base64.b64encode(out.getvalue()).decode("ascii")
        except Exception:
            logger.warning("Frame resize failed, storing original", exc_info=True)
            compressed = data.image_base64

        frame = {
            "timestamp": time.time(),
            "image_base64": compressed,
            "index": idx,
        }
        with _buf_lock:
            buf.append(frame)

        return {"ok": True, "index": idx}
    except Exception:
        logger.warning("Frame upload failed", exc_info=True)
        return {"ok": False}


@router.post("/api/visual/analyze")
async def analyze_visual(req: AnalyzeRequest):
    """Select frames from ring buffer, stitch, and call visual LLM.

    Returns {"description": str, "frames_used": int}.
    """
    buf = _get_buffer(req.session_id)
    now = time.time()

    # ── Select up to 4 frames with TTL 15s ──
    with _buf_lock:
        all_frames = [f for f in buf if now - f["timestamp"] < 15]

    if not all_frames:
        return {"description": "", "frames_used": 0}

    # Pick 4 frames: t=0 (latest), t≈-3s, t≈-6s, t≈-10s
    # Sort by timestamp ascending, then pick by target offsets
    all_frames.sort(key=lambda f: f["timestamp"])
    latest = all_frames[-1]

    def _pick(target_offset: float) -> dict:
        target_ts = latest["timestamp"] + target_offset  # negative offset
        best = all_frames[0]
        for f in all_frames:
            if abs(f["timestamp"] - target_ts) < abs(best["timestamp"] - target_ts):
                best = f
        return best

    selected = [
        _pick(-10.0),  # oldest (~10s ago)
        _pick(-6.0),
        _pick(-3.0),
        latest,        # newest
    ]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for f in selected:
        if f["index"] not in seen:
            seen.add(f["index"])
            unique.append(f)

    if not unique:
        return {"description": "", "frames_used": 0}

    # ── Stitch frames ──
    stitched = stitch_frames(unique)
    if stitched is None:
        return {"description": "", "frames_used": 0}

    # ── Call visual LLM ──
    description = analyze_frames(req.query, stitched)

    audit_log("analyze_visual", "visual", detail=req.query[:200],
              metadata={"frames_used": len(unique)})

    return {
        "description": description,
        "frames_used": len(unique),
    }


@router.get("/api/visual/latest")
async def get_latest_frame(session_id: str = "default"):
    """Return the latest frame's base64 for overlay preview."""
    buf = _get_buffer(session_id)
    with _buf_lock:
        frames = list(buf)
    if not frames:
        return {"image_base64": None}
    return {"image_base64": frames[-1]["image_base64"]}
