"""Core distillation engine — calls LLM to analyze conversation style."""

import json
import logging
import time
import uuid
import re
from datetime import datetime, timezone

from app.utils import get_llm, get_llm_model
from services.distill.models import DistilledProfile, StyleVector
from services.distill.prompts import _DISTILL_ANALYSIS_PROMPT

logger = logging.getLogger("emoji-chat")

MAX_SAMPLES = 200
MAX_TEXT_LENGTH = 15000  # characters, to fit within LLM context
MAX_RETRIES = 2
RETRY_DELAY = 2.0  # seconds


def _extract_target_messages(messages: list[dict]) -> str:
    """Filter to target messages, truncate, and concatenate for LLM analysis.

    Limits: max MAX_SAMPLES messages, max MAX_TEXT_LENGTH total characters.
    Each message is labeled [目标人物] for the analysis prompt.
    """
    target_msgs = [m for m in messages if m.get("role") == "target"]
    if not target_msgs:
        return ""

    # Take last N messages (most recent typically most representative)
    target_msgs = target_msgs[-MAX_SAMPLES:]

    lines = []
    total_chars = 0
    for i, m in enumerate(target_msgs):
        text = m["text"].strip()
        line = f"[目标人物] {text}"
        total_chars += len(line) + 1
        if total_chars > MAX_TEXT_LENGTH:
            break
        lines.append(line)

    return "\n".join(lines)


def _call_style_llm(chat_text: str) -> dict:
    """Call LLM with the style analysis prompt, return parsed JSON.

    Retries up to MAX_RETRIES times on transient failures.
    """
    client = get_llm()
    if client is None:
        raise RuntimeError("LLM client not available")

    # Truncate chat text further if needed
    if len(chat_text) > MAX_TEXT_LENGTH:
        chat_text = chat_text[:MAX_TEXT_LENGTH] + "\n... (已截断)"

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=get_llm_model(),
                messages=[
                    {"role": "system", "content": _DISTILL_ANALYSIS_PROMPT},
                    {"role": "user", "content": chat_text},
                ],
                temperature=0.1,
                max_tokens=1200,
                timeout=30.0,
            )

            raw = resp.choices[0].message.content.strip()

            # Extract JSON from response (handles markdown code fences)
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end <= start:
                raise ValueError(f"LLM response does not contain valid JSON: {raw[:200]}")

            data = json.loads(raw[start:end])

            # Validate required fields
            if "style_vector" not in data:
                raise ValueError("LLM response missing style_vector field")

            return data

        except (json.JSONDecodeError, ValueError) as e:
            # Non-retryable: bad output format
            raise
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                logger.warning(
                    "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, RETRY_DELAY, e,
                )
                time.sleep(RETRY_DELAY)

    raise RuntimeError(f"LLM call failed after {MAX_RETRIES + 1} attempts: {last_error}")


def _validate_style_vector(sv_data: dict) -> StyleVector:
    """Validate and clamp style vector values to [0, 1]."""
    dims = [
        "formality", "warmth", "humor", "verbosity",
        "figurative", "emotionality", "directness", "empathy",
    ]
    clean = {}
    for dim in dims:
        val = float(sv_data.get(dim, 0.5))
        clean[dim] = round(max(0.0, min(1.0, val)), 2)
    return StyleVector(**clean)


def analyze_style(
    messages: list[dict],
    profile_name: str,
    source: str,
) -> DistilledProfile:
    """Analyze a set of messages and return a DistilledProfile.

    Args:
        messages: List of {role, text} dicts from file_parser.
        profile_name: User-assigned name for this profile.
        source: "txt" or "json".

    Returns:
        DistilledProfile with extracted style dimensions.

    Raises:
        ValueError: If no target messages found.
        RuntimeError: If LLM call fails.
    """
    chat_text = _extract_target_messages(messages)
    if not chat_text:
        raise ValueError("未能从聊天记录中提取到目标人物的发言")

    target_count = sum(1 for m in messages if m.get("role") == "target")
    logger.info(
        "Starting style analysis: %d target messages, %d chars",
        target_count, len(chat_text),
    )

    # Call LLM for style analysis (with built-in retry)
    try:
        data = _call_style_llm(chat_text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Style analysis output parse failed", exc_info=True)
        raise RuntimeError(f"风格分析失败，LLM 返回格式异常，请重试: {str(e)[:100]}")
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("Style analysis unexpected error", exc_info=True)
        raise RuntimeError(f"风格分析失败: {str(e)[:100]}")

    # Build profile
    sv = _validate_style_vector(data.get("style_vector", {}))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    profile_id = str(uuid.uuid4())[:12]

    # Clean markers and vocabulary
    markers = []
    for m in data.get("linguistic_markers", [])[:8]:
        cleaned = re.sub(r"<[^>]*>", "", str(m).strip())
        if cleaned and len(cleaned) <= 100:
            markers.append(cleaned)

    vocab = []
    for v in data.get("vocabulary", [])[:15]:
        cleaned = re.sub(r"<[^>]*>", "", str(v).strip())
        if cleaned and len(cleaned) <= 20:
            vocab.append(cleaned)

    samples = []
    for s in data.get("sample_sentences", [])[:5]:
        cleaned = re.sub(r"<[^>]*>", "", str(s).strip())
        if cleaned and len(cleaned) <= 200:
            samples.append(cleaned)

    impression = str(data.get("overall_impression", ""))[:200]

    raw = json.dumps(data, ensure_ascii=False, indent=2)

    profile = DistilledProfile(
        id=profile_id,
        name=profile_name,
        source=source,
        created_at=now,
        updated_at=now,
        sample_count=target_count,
        style_vector=sv,
        linguistic_markers=markers,
        vocabulary=vocab,
        sample_sentences=samples,
        raw_analysis=raw,
        active=False,
    )

    logger.info(
        "Style analysis complete: profile=%s name=%s formality=%.2f warmth=%.2f",
        profile_id, profile_name, sv.formality, sv.warmth,
    )
    return profile
