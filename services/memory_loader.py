"""Load memory files and build context for the LLM system prompt."""

import os

_MEMORY_DIR = os.environ.get("MEMORY_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory"))


def _read_file(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        return f.read().strip()


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) and metadata lines."""
    lines = text.split("\n")
    result = []
    in_frontmatter = False
    for line in lines:
        if line.strip() == "---":
            in_frontmatter = not in_frontmatter
            continue
        if in_frontmatter:
            continue
        # Skip leftover metadata lines
        stripped = line.strip()
        if stripped.startswith("name:") or stripped.startswith("description:") or \
           stripped.startswith("node_type:") or stripped.startswith("originSessionId:") or \
           stripped.startswith("metadata"):
            continue
        result.append(line)
    return "\n".join(result).strip()


def get_persona() -> str:
    """Return AI persona content (raw, for display)."""
    return _read_file(os.path.join(_MEMORY_DIR, "user_persona.md"))


def get_user_profile() -> str:
    """Return user profile content (raw, for display)."""
    return _read_file(os.path.join(_MEMORY_DIR, "user_profile.md"))


def build_user_context() -> str:
    """Build the full user context to inject into the system prompt.

    Returns a ~2-3KB block with persona, user profile, and conversation memory.
    """
    parts = []

    persona = _read_file(os.path.join(_MEMORY_DIR, "user_persona.md"))
    if persona:
        persona = _strip_frontmatter(persona)
        parts.append(persona)

    profile = _read_file(os.path.join(_MEMORY_DIR, "user_profile.md"))
    if profile:
        profile = _strip_frontmatter(profile)
        parts.append("\n## 关于你正在聊天的这个人\n" + profile)

    summary = _read_file(os.path.join(_MEMORY_DIR, "conversation_summary.md"))
    if summary:
        parts.append("\n## 你和这个用户的关系历史\n" + summary)

    return "\n\n".join(parts)
