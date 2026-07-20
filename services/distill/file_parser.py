"""Parse uploaded chat history files into structured messages.

Supports:
- TXT: plain text (whole as one message),
       lines prefixed with [user]/[me]/[对方]/[target],
       or timestamp-prefixed lines like "2026-07-19 10:30 用户名: 消息"
- JSON: array of {role, content}, {from, text}, or {speaker, message}
"""

import json
import logging
import re

logger = logging.getLogger("emoji-chat")

# Common speaker name patterns in chat exports
_SPEAKER_PATTERNS = [
    # WeChat export: "用户名 2024-01-01 10:30:00"
    re.compile(r"^(\S+?)\s+\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}"),
    # QQ export: "2024-01-01 10:30:00 用户名"
    re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}\s+(\S+?)[(:]"),
    # Generic: "[用户名]" or "用户名:"
    re.compile(r"^\[([^\]]+)\]\s*"),
    re.compile(r"^([^:：]+)[:：]\s*"),
]

# Known non-speaker prefixes to skip (system messages, dates, etc.)
_SKIP_PREFIXES = {
    "系统", "System", "system", "--", "==", "日期", "Date",
    "上午", "下午", "AM", "PM",
}


def _is_skip_line(line: str) -> bool:
    """Check if a line is a system/date message, not a real utterance."""
    stripped = line.strip()
    if not stripped or len(stripped) < 2:
        return True
    for prefix in _SKIP_PREFIXES:
        if stripped.startswith(prefix):
            return True
    return False


def _parse_txt_with_speakers(text: str) -> list[dict]:
    """Parse TXT with speaker prefixes or timestamps."""
    messages = []
    current_speaker = None
    current_text = []

    for line in text.split("\n"):
        line = line.strip()
        if _is_skip_line(line):
            # Save buffered message before skipping
            if current_speaker and current_text:
                role = "target" if current_speaker != "me" else "user"
                messages.append({"role": role, "text": "\n".join(current_text).strip()})
                current_text = []
                current_speaker = None
            continue

        # Try to detect speaker prefix
        speaker = None
        remaining = line

        for pattern in _SPEAKER_PATTERNS:
            m = pattern.match(line)
            if m:
                speaker = m.group(1).strip()
                remaining = line[m.end():].strip()
                break

        if speaker:
            # New speaker detected -> save previous message
            if current_speaker and current_text:
                role = "target" if current_speaker != "me" else "user"
                messages.append({"role": role, "text": "\n".join(current_text).strip()})

            current_speaker = speaker
            current_text = [remaining] if remaining else []
        else:
            # Continuation of previous message or plain text
            if current_speaker:
                current_text.append(line)
            else:
                # No speaker detected yet, treat as target's message
                current_speaker = "target"
                current_text.append(line)

    # Save last message
    if current_speaker and current_text:
        role = "target" if current_speaker != "me" else "user"
        messages.append({"role": role, "text": "\n".join(current_text).strip()})

    return messages


def _parse_txt_plain(text: str) -> list[dict]:
    """Parse plain text — treat entire content as one target utterance."""
    text = text.strip()
    if not text:
        return []
    return [{"role": "target", "text": text}]


def _parse_json_messages(data) -> list[dict]:
    """Parse JSON array with flexible field mapping."""
    if isinstance(data, dict):
        # Try common top-level keys
        for key in ("messages", "msgs", "chat", "conversation", "history", "data"):
            if key in data:
                data = data[key]
                break

    if not isinstance(data, list):
        return []

    messages = []
    for item in data:
        if not isinstance(item, dict):
            continue

        # Detect role field
        role = None
        for role_key in ("role", "from", "speaker", "sender", "user", "name"):
            if role_key in item:
                val = str(item[role_key]).strip().lower()
                if val in ("me", "我", "user", "self"):
                    role = "user"
                else:
                    role = "target"
                break
        if role is None:
            role = "target"

        # Detect text field
        text = ""
        for text_key in ("content", "text", "message", "msg", "body"):
            if text_key in item:
                text = str(item[text_key]).strip()
                break
        if not text:
            continue

        messages.append({"role": role, "text": text})

    return messages


def parse_chat_file(content: str, source: str) -> list[dict]:
    """Parse raw file content into list of {role, text} messages.

    Args:
        content: UTF-8 decoded file content (already cleaned for XSS).
        source: "txt" or "json".

    Returns:
        List of dicts with "role" ("user"|"target") and "text" fields.
        Returns empty list if parsing fails.
    """
    if not content or not content.strip():
        return []

    if source == "json":
        try:
            data = json.loads(content)
            return _parse_json_messages(data)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON chat file")
            return []

    # TXT: try structured parsing first, fall back to plain
    messages = _parse_txt_with_speakers(content)
    if len(messages) >= 2:
        return messages

    # If structured parsing found only 0-1 message, treat as plain
    plain = _parse_txt_plain(content)
    if plain:
        return plain

    return messages
