"""User beliefs — the user's own notes/opinions, kept per domain.

These are NOT part of the RAG/graph corpus: they are the user's own assertions about a body
of knowledge. Each DOMAIN gets one small, human-editable markdown file, shared between the
live domain and every save of it — notes are about the knowledge, not the checkpoint, so
switching context never makes them vanish. (Files written by the older per-save keying are
merged in lazily on first read.) The file is injected verbatim into the answer prompt so
the expert can weigh it against the retrieved sources and, on conflict, present both
("the sources say…, while your own note holds…").

Format matches the personal memory: one compact note per line, ending with the date it was
taken — `Output floors are too strict. (2026-07-22)`. Automatic writes deduplicate and can
REPLACE a note the user reverses ("actually X is fine"), and an over-cap file triggers a
consolidation pass — never silent truncation. Small by design: a screenful of beliefs,
always in context, never retrieved or embedded.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

from app.config import state_path

_DIR = (Path(settings.beliefs_dir) if settings.beliefs_dir
        else state_path("beliefs", Path(__file__).resolve().parent.parent / ".beliefs"))
# Consolidation trigger, NOT a slice: past this, the caller runs a merge pass.
MAX_CHARS = 8000

_META = re.compile(r"\s*\((\d{4}-\d{2}-\d{2})\)\s*$")


def context_key(domain: str | None, memory: str | None = None) -> str:
    """Which file these beliefs live in: always the DOMAIN. The `memory` (save)
    parameter is accepted everywhere for API compatibility but never keys the
    file — live chat and snapshots of one domain share one set of notes."""
    return (domain or "default").strip() or "default"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120] or "default"


def _path(domain: str | None, user: str) -> Path:
    return _DIR / f"{_safe(user)}__{_safe(context_key(domain))}.md"


def _migrate(domain: str | None, memory: str | None, user: str) -> None:
    """Merge a pre-unification file keyed by this save's name into the domain
    file (missing notes only), then drop it — heals as contexts get used."""
    if not memory or _safe(memory.strip()) == _safe(context_key(domain)):
        return
    legacy = _DIR / f"{_safe(user)}__{_safe(memory.strip())}.md"
    if not legacy.exists():
        return
    current = _read_text(_path(domain, user))
    have = {(_note_of(l) or "").lower() for l in current.splitlines()}
    extra = [l.strip() for l in legacy.read_text(encoding="utf-8").splitlines()
             if _note_of(l) and _note_of(l).lower() not in have]
    if extra:
        current = (current + "\n" if current else "") + "\n".join(extra)
        _write_text(_path(domain, user), current)
    legacy.unlink()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _write_text(path: Path, text: str) -> None:
    text = (text or "").strip()
    if text:
        _DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def _note_of(line: str) -> str | None:
    """Every non-blank, non-heading line is one note (legacy `- ` tolerated)."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("- "):
        s = s[2:]
    return _META.sub("", s).strip() or None


def read_beliefs(domain: str | None = None, memory: str | None = None,
                 user: str = "default") -> str:
    _migrate(domain, memory, user)
    return _read_text(_path(domain, user))


def notes(domain: str | None = None, memory: str | None = None,
          user: str = "default") -> list[str]:
    """The context's notes, dates stripped (what the judge matches against)."""
    out = []
    for line in read_beliefs(domain, memory, user).splitlines():
        note = _note_of(line)
        if note:
            out.append(note)
    return out


def note_lines(domain: str | None = None, memory: str | None = None,
               user: str = "default") -> list[str]:
    """The raw note lines (dates included) — consolidation input."""
    return [l.strip() for l in read_beliefs(domain, memory, user).splitlines()
            if _note_of(l)]


def write_beliefs(text: str, domain: str | None = None, memory: str | None = None,
                  user: str = "default") -> int:
    """Persist (or, when empty, clear) the beliefs verbatim — the panel editor.
    Returns the stored length. Nothing is ever silently cut."""
    _migrate(domain, memory, user)
    text = (text or "").strip()
    _write_text(_path(domain, user), text)
    return len(text)


def append_belief(note: str, domain: str | None = None, memory: str | None = None,
                  user: str = "default", today: str | None = None) -> str | None:
    """Add one dated note (the chat's /note command), deduplicated against the
    context's existing notes. Returns the stored line, or None for a duplicate."""
    note = " ".join((note or "").split())
    if not note or note.lower() in {n.lower() for n in notes(domain, memory, user)}:
        return None
    line = f"{note} ({today})" if today else note
    current = read_beliefs(domain, memory, user)
    _write_text(_path(domain, user), (current + "\n" if current else "") + line)
    return line


def apply_note_operations(ops: list[tuple[str, str | None]], domain: str | None,
                          memory: str | None, user: str, today: str) -> dict:
    """The judge's note operations: (note, replaces). A note that refines or
    reverses an existing one replaces it in place (position kept, date
    refreshed); the rest append with dedup. Returns what actually changed."""
    done = {"added": [], "updated": []}
    lines = read_beliefs(domain, memory, user).splitlines()
    for note, replaces in ops:
        note = " ".join((note or "").split())
        if not note:
            continue
        if replaces:
            for i, line in enumerate(lines):
                if (_note_of(line) or "").lower() == replaces.strip().lower():
                    lines[i] = f"{note} ({today})"
                    done["updated"].append(note)
                    break
            else:
                replaces = None
        if not replaces:
            if note.lower() not in {(_note_of(l) or "").lower() for l in lines}:
                lines.append(f"{note} ({today})")
                done["added"].append(note)
    _write_text(_path(domain, user), "\n".join(lines))
    return done


def replace_notes(new_lines: list[str], domain: str | None = None,
                  memory: str | None = None, user: str = "default") -> None:
    """Swap the note lines for `new_lines` (full `note (date)` strings, the
    consolidation pass), keeping any headings the user wrote."""
    kept = [l for l in read_beliefs(domain, memory, user).splitlines()
            if l.strip() and _note_of(l) is None]
    body = [l.lstrip("- ").strip() for l in new_lines if l.strip()]
    _write_text(_path(domain, user), "\n".join(kept + body))


def delete_user_files(user: str) -> None:
    """Remove every context's beliefs for a user (guest cleanup)."""
    if _DIR.exists():
        for path in _DIR.glob(f"{_safe(user)}__*.md"):
            path.unlink(missing_ok=True)


def rename_user_files(old: str, new: str) -> None:
    """Carry every context's beliefs across an account rename."""
    if not _DIR.exists():
        return
    prefix = f"{_safe(old)}__"
    for path in _DIR.glob(f"{prefix}*.md"):
        path.replace(_DIR / f"{_safe(new)}__{path.name.removeprefix(prefix)}")
