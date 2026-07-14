"""Identity immune system — prevent AI persona drift.

Inspired by SAGE's identity drift detection: periodically checks recent
AI replies against the persona baseline. If drift exceeds threshold,
injects a correction reminder into the system prompt.

Runs every 30 turns in a background thread.
"""

import json
import logging
import os
import threading

logger = logging.getLogger("emoji-chat")

_BASE = os.path.dirname(os.path.dirname(__file__))
_CHECK_EVERY = 30
_guard_lock = threading.Lock()
_last_check_count = 0

_DRIFT_PROMPT = """你是一个人格一致性检查助手。

以下是AI角色的人设摘要：
{persona_summary}

以下是最近的AI回复：
{recent_replies}

请评估这些回复与AI人设的一致性。返回一个JSON：
{{"drift_score": 0.0-1.0, "issues": ["问题1", "问题2"], "correction": "修正建议"}}

评分标准：
- 0.0-0.3: 完全符合人设
- 0.3-0.5: 有轻微偏离但可接受
- 0.5-0.7: 明显偏离，需要注意
- 0.7-1.0: 严重偏离，需要立即修正

只输出JSON，不要其他内容。"""


def _load_recent_replies(n: int = 5) -> list[str]:
    """Load the last N AI replies from conversation archive."""
    archive = os.path.join(_BASE, "memory", "conversation_archive.jsonl")
    replies = []
    try:
        if os.path.exists(archive):
            with open(archive) as f:
                lines = f.readlines()
            for line in reversed(lines):
                try:
                    rec = json.loads(line)
                    assistant = rec.get("assistant", "")
                    if assistant:
                        replies.append(assistant)
                        if len(replies) >= n:
                            break
                except Exception:
                    pass
    except Exception:
        pass
    return list(reversed(replies))


def _load_persona_summary(max_chars: int = 500) -> str:
    """Load the first max_chars of user_persona.md as summary."""
    path = os.path.join(_BASE, "memory", "user_persona.md")
    try:
        if os.path.exists(path):
            with open(path) as f:
                text = f.read().strip()
                lines = text.split("\n")
                # Skip frontmatter and heading
                body = []
                for line in lines:
                    if line.startswith("#") or line.startswith("---"):
                        continue
                    body.append(line)
                return "\n".join(body)[:max_chars]
    except Exception:
        pass
    return ""


def _check_drift() -> dict | None:
    """Call LLM to check for persona drift.

    Returns {"drift_score": float, "issues": list, "correction": str} or None.
    """
    persona = _load_persona_summary()
    if not persona:
        return None

    replies = _load_recent_replies(5)
    if len(replies) < 3:
        return None

    from app.routes.chat import _get_llm
    client = _get_llm()

    numbered = "\n".join(f"{i+1}. {r[:120]}" for i, r in enumerate(replies))
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": _DRIFT_PROMPT.format(
                    persona_summary=persona,
                    recent_replies=numbered,
                )},
                {"role": "user", "content": "请评估以上回复与人设的一致性。"},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content.strip()
        # Extract JSON
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        pass
    return None


def _load_drift_log() -> list[dict]:
    """Load drift history."""
    path = os.path.join(_BASE, "memory", "drift_log.jsonl")
    entries = []
    try:
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return entries


def _save_drift(drift_data: dict):
    """Append drift check result to log."""
    path = os.path.join(_BASE, "memory", "drift_log.jsonl")
    try:
        with open(path, "a") as f:
            f.write(json.dumps(drift_data, ensure_ascii=False) + "\n")
    except Exception:
        pass


def maybe_guard():
    """Check for persona drift every _CHECK_EVERY turns.

    Runs in background thread. If drift is detected, logs it for
    trend analysis and enables correction injection.
    """
    global _last_check_count
    if not _guard_lock.acquire(blocking=False):
        return
    try:
        archive = os.path.join(_BASE, "memory", "conversation_archive.jsonl")
        if not os.path.exists(archive):
            return
        with open(archive) as f:
            line_count = sum(1 for _ in f)
        if line_count - _last_check_count < _CHECK_EVERY:
            return
        _last_check_count = line_count

        result = _check_drift()
        if not result:
            return

        drift_score = result.get("drift_score", 0)
        issues = result.get("issues", [])
        correction = result.get("correction", "")

        entry = {
            "turn_count": line_count,
            "drift_score": drift_score,
            "issues": issues,
            "correction": correction,
        }
        _save_drift(entry)

        if drift_score > 0.5:
            logger.warning(
                "Persona drift detected: score=%.2f, issues=%s",
                drift_score, issues,
            )
        else:
            logger.info("Identity check passed: drift_score=%.2f", drift_score)
    except Exception:
        pass
    finally:
        _guard_lock.release()


def get_drift_correction() -> str:
    """Return a correction reminder if recent drift was significant.

    Called during _build_context() to inject correction into system prompt.
    """
    entries = _load_drift_log()
    if not entries:
        return ""

    latest = entries[-1]
    score = latest.get("drift_score", 0)
    if score < 0.5:
        return ""

    correction = latest.get("correction", "")
    issues = latest.get("issues", [])

    lines = [
        "⚠️ 身份一致性提醒：",
        f"你最近的回复有些偏离了你的核心性格（偏离度{score:.2f}）。",
    ]
    if issues:
        lines.append(f"具体问题：{'；'.join(issues[:3])}")
    if correction:
        lines.append(f"修正方向：{correction}")
    lines.append("请在接下来的回复中回归你的人设。")

    return "\n".join(lines)
