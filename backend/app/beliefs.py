"""User beliefs — the user's own notes/opinions, kept per memory context.

These are NOT part of the RAG/graph corpus: they are the user's own assertions about a body
of knowledge. Each memory context (a saved snapshot, or the live domain) gets one small,
human-editable markdown file. It is injected verbatim into the answer prompt so the expert
can weigh it against the retrieved sources and, on conflict, present both ("the sources
say…, while your own note holds…"). Small by design — a handful of beliefs, always in
context, never retrieved or embedded.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

_DIR = Path(settings.beliefs_dir) if settings.beliefs_dir else Path(__file__).resolve().parent.parent / ".beliefs"
MAX_CHARS = 8000  # keep it context-sized: a screenful of beliefs, not a corpus


def context_key(domain: str | None, memory: str | None) -> str:
    """Which memory context these beliefs belong to: the selected save, else the live
    domain. Matches exactly what the chat answers from, so the editor and the pipeline agree."""
    return (memory or domain or "default").strip() or "default"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120] or "default"


def _path(domain: str | None, memory: str | None, user: str) -> Path:
    return _DIR / f"{_safe(user)}__{_safe(context_key(domain, memory))}.md"


def read_beliefs(domain: str | None = None, memory: str | None = None, user: str = "default") -> str:
    try:
        return _path(domain, memory, user).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_beliefs(text: str, domain: str | None = None, memory: str | None = None,
                  user: str = "default") -> int:
    """Persist (or, when empty, clear) the beliefs for a context. Returns the stored length."""
    text = (text or "").strip()[:MAX_CHARS]
    path = _path(domain, memory, user)
    if text:
        _DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    elif path.exists():
        path.unlink()
    return len(text)


def delete_user_files(user: str) -> None:
    """Remove every context's beliefs for a user (guest cleanup)."""
    if _DIR.exists():
        for path in _DIR.glob(f"{_safe(user)}__*.md"):
            path.unlink(missing_ok=True)


def append_belief(note: str, domain: str | None = None, memory: str | None = None,
                  user: str = "default") -> int:
    """Add one note as a bullet to a context's beliefs (used by the chat's /note command).
    Keeps whatever was already there — the panel and /note write to the same file."""
    note = " ".join((note or "").split())
    if not note:
        return len(read_beliefs(domain, memory, user))
    current = read_beliefs(domain, memory, user)
    combined = f"{current}\n- {note}" if current else f"- {note}"
    return write_beliefs(combined, domain, memory, user)
