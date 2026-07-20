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


def load_markdown(user: str) -> str:
    """The user's memory file VERBATIM (the default header when it doesn't exist).

    The file is the source of truth and is edited as free markdown in the panel;
    only its '- ' bullet lines are facts (what the judge and the chat read). Every
    automatic operation below edits bullet lines ONLY — prose, headings and blank
    lines the user writes around them survive untouched."""
    try:
        return _path(user).read_text(encoding="utf-8")
    except FileNotFoundError:
        return _HEADER


def save_markdown(text: str, user: str) -> list[str]:
    """Write the file verbatim (the panel's markdown editor). Returns the facts
    parsed back from its bullet lines."""
    _DIR.mkdir(parents=True, exist_ok=True)
    text = text or _HEADER
    if not text.endswith("\n"):
        text += "\n"
    _path(user).write_text(text, encoding="utf-8")
    return _parse(text)


def load_memories(user: str) -> list[str]:
    """Return this user's saved facts (the bullet lines)."""
    return _parse(load_markdown(user))


def _fact_of(line: str) -> str | None:
    s = line.strip()
    if s.startswith("- "):
        return s[2:].strip() or None
    return None


def add_memory(fact: str, user: str) -> list[str]:
    """Append a fact bullet (trimmed, de-duplicated) and persist. Returns the list."""
    fact = " ".join(fact.split())
    if not fact or fact in load_memories(user):
        return load_memories(user)
    text = load_markdown(user)
    if not text.endswith("\n"):
        text += "\n"
    return save_markdown(text + f"- {fact}\n", user)


def remove_memory(fact: str, user: str) -> list[str]:
    """Remove one fact's bullet line (exact match) and persist. Returns the list."""
    kept = [l for l in load_markdown(user).splitlines() if _fact_of(l) != fact]
    return save_markdown("\n".join(kept), user)


def clear_memories(user: str) -> list[str]:
    """Wipe this user's saved facts. Returns the now-empty list."""
    _save([], user)
    return []


def apply_operations(user: str, add: list[str], update: list[tuple[str, str]],
                     delete: list[str]) -> list[str]:
    """Evolve the memory with the judge's operations, editing ONLY bullet lines:
    updates replace a fact's line in place (it keeps its position and indent),
    deletes drop the line, adds append at the end. Anything else in the markdown
    is the user's and stays byte-identical. Returns the new fact list."""
    updates = dict(update)
    gone = set(delete)
    lines = []
    for line in load_markdown(user).splitlines():
        fact = _fact_of(line)
        if fact is None:
            lines.append(line)
        elif fact in gone:
            continue
        elif fact in updates:
            indent = line[: len(line) - len(line.lstrip())]
            lines.append(f"{indent}- {updates[fact]}")
        else:
            lines.append(line)
    text = "\n".join(lines)
    existing = set(_parse(text))
    fresh = []
    for fact in add:
        fact = " ".join(fact.split())
        if fact and fact not in existing:
            fresh.append(f"- {fact}")
            existing.add(fact)
    if fresh:
        text = text.rstrip("\n") + "\n" + "\n".join(fresh)
    return save_markdown(text, user)


def replace_all(user: str, memories: list[str]) -> list[str]:
    """Swap the fact bullets for `memories` (the consolidation pass) while keeping
    every non-bullet line the user may have written. Returns the new list."""
    kept = [l for l in load_markdown(user).splitlines() if _fact_of(l) is None]
    text = "\n".join(kept).rstrip("\n")
    bullets = "\n".join(f"- {m}" for m in memories)
    text = (text + "\n\n" if text.strip() else "") + bullets
    return save_markdown(text, user)


def delete_user(user: str) -> None:
    """Remove the user's memory file entirely (guest cleanup)."""
    _path(user).unlink(missing_ok=True)


def rename_user(old: str, new: str) -> None:
    """Carry the memory file across an account rename."""
    src = _path(old)
    if src.exists():
        src.replace(_path(new))


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
