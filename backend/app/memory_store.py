"""Persistent user memory — the facts saved via /remember and the memory judge.

Per-account: each user gets one editable Markdown file (one fact per `- ` line) under
backend/data/memory/, so it's a human-readable, hand-editable source-of-record — the
SOTA-aligned format for personal memory (matching the beliefs files and Anthropic's
/memories / Claude's own Markdown memory) rather than opaque JSON. The character/persona
is deliberately NOT here: it's per-session and lives only in the frontend.

Files are disposable/regenerable — delete one to reset that user's memory. The pre-account
global files (app/memory.md, app/memory.json) are left untouched; copy one to
data/memory/<username>.md to hand its facts to an account. Paths use pathlib + UTF-8 so
the same code runs on Mac and the enterprise Windows box.
"""

from __future__ import annotations

import re
from pathlib import Path

# Gitignored — these hold personal facts.
from app.config import state_path

_DIR = state_path("memory", Path(__file__).resolve().parents[1] / "data" / "memory")

_HEADER = (
    "# User memory\n\n"
    "Durable facts about the user, saved via /remember and the memory judge. "
    "Hand-editable — one fact per `- ` line.\n\n"
)


def _path(user: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", user)[:120] or "default"
    return _DIR / f"{safe}.md"


def load_memories(user: str) -> list[str]:
    """Return this user's saved facts."""
    try:
        return _parse(_path(user).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def add_memory(fact: str, user: str) -> list[str]:
    """Append a fact (trimmed, de-duplicated) and persist. Returns the new list."""
    fact = " ".join(fact.split())
    memories = load_memories(user)
    if fact and fact not in memories:
        memories.append(fact)
        _save(memories, user)
    return memories


def remove_memory(fact: str, user: str) -> list[str]:
    """Remove one fact (exact match) and persist. Returns the updated list."""
    memories = [m for m in load_memories(user) if m != fact]
    _save(memories, user)
    return memories


def clear_memories(user: str) -> list[str]:
    """Wipe this user's saved facts. Returns the now-empty list."""
    _save([], user)
    return []


def delete_user(user: str) -> None:
    """Remove the user's memory file entirely (guest cleanup)."""
    _path(user).unlink(missing_ok=True)


def _parse(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- "):
            fact = s[2:].strip()
            if fact:
                out.append(fact)
    return out


def _save(memories: list[str], user: str) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f"- {m}" for m in memories)
    _path(user).write_text(_HEADER + (body + "\n" if body else ""), encoding="utf-8")
