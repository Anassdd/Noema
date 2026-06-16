"""Persistent user memory — the facts saved via /remember.

Stored as a JSON file on local disk so it survives restarts and is shared across
sessions. The character/persona is deliberately NOT here: it's per-session and
lives only in the frontend.

The file is disposable/regenerable — delete it to reset memory. Paths use
pathlib and UTF-8 so the same code runs on Mac and the enterprise Windows box.
"""

from __future__ import annotations

import json
from pathlib import Path

# Sits next to this module. Gitignored — it can hold personal facts.
_MEMORY_PATH = Path(__file__).resolve().parent / "memory.json"


def load_memories() -> list[str]:
    """Return the saved facts, or an empty list if the file is missing/corrupt."""
    if not _MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    memories = data.get("memories", []) if isinstance(data, dict) else []
    return [m for m in memories if isinstance(m, str)]


def add_memory(fact: str) -> list[str]:
    """Append a fact (trimmed, de-duplicated) and persist. Returns the new list."""
    fact = fact.strip()
    memories = load_memories()
    if fact and fact not in memories:
        memories.append(fact)
        _save(memories)
    return memories


def remove_memory(fact: str) -> list[str]:
    """Remove one fact (exact match) and persist. Returns the updated list."""
    memories = [m for m in load_memories() if m != fact]
    _save(memories)
    return memories


def clear_memories() -> list[str]:
    """Wipe all saved facts. Returns the now-empty list."""
    _save([])
    return []


def _save(memories: list[str]) -> None:
    _MEMORY_PATH.write_text(
        json.dumps({"memories": memories}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
