"""Persistent user memory — the facts saved via /remember and the memory judge.

Stored as an editable Markdown file (one fact per `- ` line) so it's a human-readable,
hand-editable source-of-record — the SOTA-aligned format for personal memory (matching the
beliefs files and Anthropic's /memories / Claude's own Markdown memory) rather than opaque JSON.
The character/persona is deliberately NOT here: it's per-session and lives only in the frontend.

The file is disposable/regenerable — delete it to reset memory. A pre-existing legacy
`memory.json` is migrated to Markdown on first load. Paths use pathlib + UTF-8 so the same code
runs on Mac and the enterprise Windows box.
"""

from __future__ import annotations

import json
from pathlib import Path

# Both sit next to this module. Gitignored — they can hold personal facts.
_MD_PATH = Path(__file__).resolve().parent / "memory.md"
_JSON_PATH = Path(__file__).resolve().parent / "memory.json"  # legacy, migrated once on load

_HEADER = (
    "# User memory\n\n"
    "Durable facts about the user, saved via /remember and the memory judge. "
    "Hand-editable — one fact per `- ` line.\n\n"
)


def load_memories() -> list[str]:
    """Return the saved facts. Reads Markdown; if only the legacy JSON exists, migrate it."""
    if _MD_PATH.exists():
        return _parse(_MD_PATH.read_text(encoding="utf-8"))
    legacy = _load_legacy_json()
    if legacy:
        _save(legacy)  # migrate JSON → Markdown once; the JSON is left as a harmless backup
    return legacy


def add_memory(fact: str) -> list[str]:
    """Append a fact (trimmed, de-duplicated) and persist. Returns the new list."""
    fact = " ".join(fact.split())
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


def _parse(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("- "):
            fact = s[2:].strip()
            if fact:
                out.append(fact)
    return out


def _load_legacy_json() -> list[str]:
    if not _JSON_PATH.exists():
        return []
    try:
        data = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    memories = data.get("memories", []) if isinstance(data, dict) else []
    return [m for m in memories if isinstance(m, str)]


def _save(memories: list[str]) -> None:
    body = "\n".join(f"- {m}" for m in memories)
    _MD_PATH.write_text(_HEADER + (body + "\n" if body else ""), encoding="utf-8")
