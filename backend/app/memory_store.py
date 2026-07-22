"""Three-file personal memory — profile / now / history, one directory per account.

The layout mirrors what the frontier products converged on (verified against the
real Claude.ai and ChatGPT memory UIs, 2026-07):

- profile.md — a TOPICAL document about the user, Claude/ChatGPT-style: `## Topic`
  sections (Identity, Work, Preferences, Projects…) each holding a short paragraph
  of connected prose. New facts are woven INTO the right section by rewriting it —
  the section is the unit of change, so related facts live together instead of
  piling up as separate lines. Always injected.
- now.md     — the CURRENT, time-bound situation as dated one-line facts; a fact
  may carry an end date, and expired facts are retired automatically at session
  start. A list on purpose: each item needs its own expiry.
- history.md — where retired facts land with their date range. Never injected
  wholesale — but nothing the memory knew is silently lost.
- journal.md — the diary of conversations: one dated line per chat per day,
  written by a lazy daily pass over the conversation store (ChatGPT's
  recent-chats layer, at a tenth of the size). Only its TAIL is injected.

The two archives are reachable on demand: `recall()` scores history+journal
lines against a query by token overlap (no embeddings — personal facts stay out
of the vector stores), so "when was I in Paris?" works without paying any
standing context for the archive tiers.

profile+now are capped (chars): the injected block stays small forever, and
hitting a cap forces a consolidation pass instead of unbounded growth — that
curation pressure is what keeps the memory dense and connected.

Dates: a profile section heading ends with `(YYYY-MM-DD)` = last updated; a now
fact ends with `(YYYY-MM-DD)` = learned or `(YYYY-MM-DD → YYYY-MM-DD)` = learned →
holds-until. Files are hand-editable markdown; paths use pathlib + UTF-8 so the
same code runs on Mac and the enterprise Windows box.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# Gitignored — these hold personal facts.
from app.config import state_path

_DIR = state_path("memory", Path(__file__).resolve().parents[1] / "data" / "memory")

FILES = ("profile", "now", "history", "journal")
LIVE_FILES = ("profile", "now")

# The journal is uncapped like history, but only its tail rides in the prompt,
# and past this size the oldest entries get compacted into per-month digests.
JOURNAL_TAIL_CHARS = 800
JOURNAL_COMPACT_AT = 12000

# Character caps on the two injected files (whole file text), env-tunable. Defaults
# sit at frontier-product scale (ChatGPT's saved memory ≈ 5–8k chars). The cap's
# job is the consolidation WALL, not scarcity. History is uncapped by design:
# never injected, and an uncapped archive is what lets consolidation retire
# instead of erase.
CAPS = {
    "profile": int(os.getenv("MEMORY_PROFILE_CAP", "6000")),
    "now": int(os.getenv("MEMORY_NOW_CAP", "2000")),
}

# Default headers earlier versions wrote into the files — stripped on load (and
# thereby healed on the next save) so the editor shows content only.
_LEGACY_HEADERS = (
    "# User memory\n\n"
    "Durable facts about the user, saved via /remember and the memory judge. "
    "Hand-editable — one fact per `- ` line.\n\n",
    "# Profile\n\n"
    "Durable facts about the user — identity, role, stable preferences. "
    "One fact per `- ` line; the date in parentheses is when it was learned.\n\n",
    "# Now\n\n"
    "The user's current, time-bound situation. `(learned → until)` dates mark "
    "how long a fact holds; expired facts move to history automatically.\n\n",
    "# History\n\n"
    "Retired facts with their date range — no longer current, never lost. "
    "This file is not injected into chats.\n\n",
)

# Trailing metadata paren: (learned) or (learned → until) on a now/history line,
# (updated) on a profile section heading.
_META = re.compile(r"\s*\((\d{4}-\d{2}-\d{2})(?:\s*→\s*(\d{4}-\d{2}-\d{2}))?\)\s*$")
_SECTION = re.compile(r"^##\s+(.+)$")


def _dir(user: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", user)[:120] or "default"
    return _DIR / safe


def _path(user: str, name: str) -> Path:
    if name not in FILES:
        raise ValueError(f"unknown memory file: {name}")
    return _dir(user) / f"{name}.md"


def _migrate(user: str) -> None:
    """Carry a pre-split single-file memory (`<user>.md`) into the directory
    layout: the old file becomes profile.md verbatim — nothing is reformatted."""
    legacy = _DIR / f"{_dir(user).name}.md"
    if legacy.exists() and not _dir(user).exists():
        _dir(user).mkdir(parents=True, exist_ok=True)
        legacy.replace(_path(user, "profile"))


def load_file(user: str, name: str) -> str:
    """One memory file (empty string when it doesn't exist). A boilerplate
    header written by an earlier version is stripped here — the next save
    heals the file on disk."""
    _migrate(user)
    try:
        text = _path(user, name).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    for header in _LEGACY_HEADERS:
        if text.startswith(header):
            return text[len(header):].lstrip("\n")
    return text


def load_files(user: str) -> dict[str, str]:
    return {name: load_file(user, name) for name in FILES}


def save_file(user: str, name: str, text: str) -> str:
    """Write one file verbatim (the settings editor). Returns the saved text."""
    _migrate(user)
    _dir(user).mkdir(parents=True, exist_ok=True)
    text = text or ""
    if text and not text.endswith("\n"):
        text += "\n"
    _path(user, name).write_text(text, encoding="utf-8")
    return text


def usage(user: str) -> dict[str, dict]:
    """Fill levels for the capped live files — the Hermes-style gauge."""
    return {
        name: {"chars": len(load_file(user, name)), "cap": CAPS[name]}
        for name in LIVE_FILES
    }


# ---------------------------------------------------------------- profile ----
# The profile is `## Topic (updated)` sections of prose. Text before the first
# heading (the preamble) is the user's own and survives every operation.

def _clean_title(raw: str) -> str:
    return _META.sub("", raw.lstrip("#").strip()).strip()


def sections(user: str) -> list[tuple[str, str]]:
    """The profile's (title, body) pairs, in order, dates stripped from titles."""
    out = []
    for title, body in _split_profile(load_file(user, "profile"))[1]:
        out.append((_clean_title(title), body.strip()))
    return out


def section_titles(user: str) -> list[str]:
    return [t for t, _ in sections(user)]


def section_body(user: str, title: str) -> str:
    for t, body in sections(user):
        if t.lower() == title.strip().lower():
            return body
    return ""


def _split_profile(text: str) -> tuple[str, list[tuple[str, str]]]:
    """-> (preamble, [(raw heading text, body)])."""
    preamble: list[str] = []
    parts: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            parts.append((m.group(1), []))
        elif parts:
            parts[-1][1].append(line)
        else:
            preamble.append(line)
    return ("\n".join(preamble).strip(),
            [(head, "\n".join(body)) for head, body in parts])


def write_section(user: str, title: str, text: str, today: str) -> None:
    """Create or fully rewrite one `## Topic` section — the judge's unit of
    change. The heading takes today as its updated-date; an empty text removes
    the section. Hash lines inside the body are defused so a stray heading in
    model output can never split the document."""
    title = _clean_title(title)
    if not title:
        return
    body = "\n".join(l.lstrip("# ") if l.lstrip().startswith("#") else l
                     for l in (text or "").strip().splitlines()).strip()
    preamble, parts = _split_profile(load_file(user, "profile"))
    kept, replaced = [], False
    for head, old_body in parts:
        if _clean_title(head).lower() == title.lower():
            replaced = True
            if body:
                kept.append((f"{title} ({today})", body))
        else:
            kept.append((head, old_body.strip()))
    if body and not replaced:
        kept.append((f"{title} ({today})", body))

    blocks = ([preamble] if preamble else []) + \
        [f"## {head}\n{b}" for head, b in kept if b]
    save_file(user, "profile", "\n\n".join(blocks))


def remove_section(user: str, title: str) -> bool:
    if title.strip().lower() not in {t.lower() for t in section_titles(user)}:
        return False
    write_section(user, title, "", "")
    return True


# -------------------------------------------------------------------- now ----

def _fact_of(line: str) -> str | None:
    """Every non-blank, non-heading line is one fact — plain sentences. A
    leading `- ` (legacy files) is tolerated and dropped."""
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("- "):
        s = s[2:]
    return _META.sub("", s).strip() or None


def _meta_of(line: str) -> tuple[str | None, str | None]:
    m = _META.search(line.strip())
    return (m.group(1), m.group(2)) if m else (None, None)


def _entry(fact: str, learned: str, until: str | None = None) -> str:
    dates = f"{learned} → {until}" if until else learned
    return f"{fact} ({dates})"


def facts(user: str, name: str) -> list[str]:
    """The file's fact lines, metadata stripped (what the judge matches on)."""
    out = []
    for line in load_file(user, name).splitlines():
        fact = _fact_of(line)
        if fact:
            out.append(fact)
    return out


def fact_lines(user: str, name: str) -> list[str]:
    """The raw fact lines (dates included) — what the judge reads."""
    return [l.strip() for l in load_file(user, name).splitlines() if _fact_of(l)]


def live_facts(user: str) -> list[str]:
    """What the panel badge and /forget can address: profile topics + now facts."""
    return section_titles(user) + facts(user, "now")


def context_block(user: str) -> str | None:
    """The injection block: the profile document verbatim, the Now list, and
    the journal's tail. None when empty. History never appears here — it (and
    the journal's full depth) is reached through recall() instead."""
    parts = []
    profile = load_file(user, "profile").strip()
    if profile:
        parts.append(profile)
    now = fact_lines(user, "now")
    if now:
        parts.append("## Now\n" + "\n".join(now))
    tail = journal_tail(user)
    if tail:
        parts.append("## Recent chats\n" + "\n".join(tail))
    return "\n\n".join(parts) if parts else None


def journal_tail(user: str) -> list[str]:
    """The newest journal lines that fit the injection budget, oldest first."""
    lines = [l.strip() for l in load_file(user, "journal").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    tail: list[str] = []
    used = 0
    for line in reversed(lines):
        if used + len(line) > JOURNAL_TAIL_CHARS and tail:
            break
        tail.append(line)
        used += len(line)
    return tail[::-1]


def append_journal(user: str, lines: list[str],
                   sources: list[str] | None = None) -> None:
    """Append journal lines. `sources` (parallel conversation ids) feed the
    provenance sidecar — the industry pattern for derived data: the journal
    file stays clean human markdown, and a separate index remembers which
    conversation each line came from so deletion can cascade."""
    if not lines:
        return
    text = load_file(user, "journal")
    if text and not text.endswith("\n"):
        text += "\n"
    save_file(user, "journal", text + "\n".join(lines) + "\n")
    if sources:
        index = _journal_index(user)
        for line, source in zip(lines, sources):
            index.setdefault(source, []).append(line.strip())
        _save_journal_index(user, index)


_JOURNAL_INDEX = ".journal-index.json"


def _journal_index(user: str) -> dict[str, list[str]]:
    try:
        return json.loads((_dir(user) / _JOURNAL_INDEX).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_journal_index(user: str, index: dict[str, list[str]]) -> None:
    _dir(user).mkdir(parents=True, exist_ok=True)
    (_dir(user) / _JOURNAL_INDEX).write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8")


def forget_conversation(user: str, conversation_id: str) -> bool:
    """Cascade a conversation deletion into the journal: drop the lines it
    produced (exact match only — a line the user has since edited is theirs
    and survives). Returns True when the conversation had journal lines."""
    index = _journal_index(user)
    targets = index.pop(conversation_id, None)
    if targets is None:
        return False
    lines = load_file(user, "journal").splitlines()
    for target in targets:
        for i, line in enumerate(lines):
            if line.strip() == target:
                del lines[i]
                break
    save_file(user, "journal", "\n".join(lines))
    _save_journal_index(user, index)
    return True


def prune_journal_index(user: str) -> None:
    """Drop index rows whose lines are gone (compacted into digests or edited
    away) — their provenance ended with them; digests are past cascading."""
    present = {l.strip() for l in load_file(user, "journal").splitlines()}
    pruned = {}
    for source, lines in _journal_index(user).items():
        kept = [l for l in lines if l in present]
        if kept:
            pruned[source] = kept
    _save_journal_index(user, pruned)


def add_fact(user: str, fact: str, today: str, until: str | None = None) -> bool:
    """Append one dated fact line to now.md (trimmed, deduplicated)."""
    fact = " ".join(fact.split())
    if not fact or fact.lower() in {f.lower() for f in facts(user, "now")}:
        return False
    text = load_file(user, "now")
    if text and not text.endswith("\n"):
        text += "\n"
    save_file(user, "now", text + _entry(fact, today, until) + "\n")
    return True


def remove_fact(user: str, fact: str) -> None:
    """Drop one now-fact's line — or, when `fact` names a profile topic, that
    whole section (how /forget addresses the profile)."""
    target = fact.strip().lower()
    kept = [l for l in load_file(user, "now").splitlines()
            if (_fact_of(l) or "").lower() != target]
    save_file(user, "now", "\n".join(kept))
    remove_section(user, fact)


def replace_now(user: str, entries: list[str]) -> None:
    """Swap now.md's fact lines for `entries` (full `fact (dates)` strings, the
    consolidation pass), keeping any headings the user wrote."""
    kept = [l for l in load_file(user, "now").splitlines() if _fact_of(l) is None]
    text = "\n".join(kept).rstrip("\n")
    body = "\n".join(e.lstrip("- ").strip() for e in entries if e.strip())
    save_file(user, "now", (text + "\n\n" if text.strip() else "") + body)


def append_history(user: str, lines: list[str]) -> None:
    if not lines:
        return
    text = load_file(user, "history")
    if text and not text.endswith("\n"):
        text += "\n"
    save_file(user, "history", text + "\n".join(lines) + "\n")


def apply_now_operations(user: str, ops: dict, today: str) -> dict:
    """Evolve now.md with the judge's line operations:
    ops: {"add": [(fact, until)], "update": [(old, new, until)],
          "delete": [old], "retire": [(old, as_text)]}
    Updates replace in place (position kept, date refreshed — the fact was just
    re-confirmed); retires carry the original learned date into history.
    Returns what actually changed."""
    done = {"added": [], "updated": [], "removed": [], "retired": []}
    lines = load_file(user, "now").splitlines()
    archived: list[str] = []

    def edit(old: str, replacement: str | None) -> str | None:
        for i, line in enumerate(lines):
            if (_fact_of(line) or "").lower() == old.strip().lower():
                learned, _ = _meta_of(line)
                if replacement is None:
                    del lines[i]
                else:
                    lines[i] = replacement
                return learned or today
        return None

    for old, new, until in ops.get("update", []):
        if edit(old, _entry(" ".join(new.split()), today, until)):
            done["updated"].append(new)

    for old in ops.get("delete", []):
        if edit(old, None):
            done["removed"].append(old)

    for old, as_text in ops.get("retire", []):
        learned = edit(old, None)
        if learned:
            archived.append(_entry(" ".join((as_text or old).split()), learned, today))
            done["retired"].append(as_text or old)

    save_file(user, "now", "\n".join(lines))

    for fact, until in ops.get("add", []):
        if add_fact(user, fact, today, until):
            done["added"].append(" ".join(fact.split()))

    append_history(user, archived)
    return done


def expired(user: str, today: str) -> list[tuple[str, str, str]]:
    """now-facts whose until-date has passed: [(fact, learned, until)]."""
    out = []
    for line in load_file(user, "now").splitlines():
        fact = _fact_of(line)
        learned, until = _meta_of(line)
        if fact and until and until < today:
            out.append((fact, learned, until))
    return out


def retire_facts(user: str, rewrites: list[tuple[str, str]]) -> list[str]:
    """The expiry sweep's mechanical half: move each (fact, past-tense rewrite)
    from now.md to history.md, ending its range at its own until-date. Returns
    the retired rewrites."""
    retired = []
    for fact, as_text in rewrites:
        for f, learned, until in expired(user, "9999-12-31"):
            if f.lower() == fact.strip().lower():
                remove_fact(user, fact)
                append_history(user, [_entry(" ".join(as_text.split()), learned, until)])
                retired.append(as_text)
                break
    return retired


# ------------------------------------------------------------------ recall ----
# On-demand access to the archive tiers (history + journal) — IDF-weighted
# token scoring, deliberately embedding-free. Runs on EVERY message (it costs
# no LLM call), so relevance is enforced by the score threshold, never by a
# brittle "is this about the past?" gate: a phrasing the gate would miss can
# no longer hide the archive.

_STOPWORDS = frozenset(
    "the and was were did does has have had for with about when what where "
    "which that this from say says said ever been over your you our are not "
    "les des une dans avec pour que qui est ete été sur par nous vous elle il "
    "comment quand quoi dire dit user".split()
)


def _tokens(text: str) -> set[str]:
    import unicodedata
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return {t for t in re.findall(r"[a-z0-9]{3,}", flat) if t not in _STOPWORDS}


def recall(user: str, query: str, wide: bool = False) -> list[str]:
    """Archive lines (history + journal) relevant to `query`.

    Every line is scored by the IDF-weighted share of the query's content
    tokens it covers — rare words ("istanbul") dominate common ones. `wide`
    (the message *explicitly* references the past) lowers the bar and returns
    more lines; otherwise only a strong match with at least one rare token
    qualifies, so ordinary corpus questions don't drag archive noise along.
    Empty when nothing clears the bar — callers inject nothing then."""
    import math

    qtok = _tokens(query)
    if not qtok:
        return []
    docs = []
    for name in ("history", "journal"):
        for pos, line in enumerate(load_file(user, name).splitlines()):
            s = line.strip()
            if s and not s.startswith("#"):
                docs.append((pos, s, _tokens(s)))
    if not docs:
        return []

    df = {t: sum(1 for _p, _l, toks in docs if t in toks) for t in qtok}
    idf = {t: math.log1p(len(docs) / df[t]) for t in qtok if df[t]}
    if not idf:
        return []
    denom = sum(idf.values())
    # "Rare" = absent from most of the archive. The floor of 2 keeps small
    # archives honest — a token in 2 of 4 lines is still a real signal; the
    # coverage bar, not this flag, is the primary filter.
    rare_cutoff = max(2, round(len(docs) * 0.34))

    min_coverage, limit = (0.15, 6) if wide else (0.6, 3)
    scored = []
    for pos, line, toks in docs:
        matched = qtok & toks
        if not matched:
            continue
        coverage = sum(idf.get(t, 0.0) for t in matched) / denom
        has_rare = any(df.get(t, 0) <= rare_cutoff for t in matched)
        if coverage >= min_coverage and (wide or has_rare):
            scored.append((-coverage, -pos, line))
    return [line for *_ignored, line in sorted(scored)[:limit]]


# ------------------------------------------------------------------ stamps ----

_SWEEP_STAMP = ".last-sweep"
_JOURNAL_STAMP = ".journal-stamp"


def sweep_due(user: str, today: str) -> bool:
    """True once per day — the lazy session-start expiry check."""
    try:
        return (_dir(user) / _SWEEP_STAMP).read_text(encoding="utf-8").strip() != today
    except FileNotFoundError:
        return True


def mark_swept(user: str, today: str) -> None:
    _dir(user).mkdir(parents=True, exist_ok=True)
    (_dir(user) / _SWEEP_STAMP).write_text(today, encoding="utf-8")


def journal_stamp(user: str) -> str:
    """ISO timestamp of the last journal pass ('' = never ran)."""
    try:
        return (_dir(user) / _JOURNAL_STAMP).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def mark_journal(user: str, timestamp: str) -> None:
    _dir(user).mkdir(parents=True, exist_ok=True)
    (_dir(user) / _JOURNAL_STAMP).write_text(timestamp, encoding="utf-8")


def clear(user: str) -> None:
    """Wipe the whole memory — all three files (the settings 'Clear memory')."""
    for name in FILES:
        _path(user, name).unlink(missing_ok=True)
    (_dir(user) / _SWEEP_STAMP).unlink(missing_ok=True)
    (_dir(user) / _JOURNAL_STAMP).unlink(missing_ok=True)
    (_dir(user) / _JOURNAL_INDEX).unlink(missing_ok=True)


def delete_user(user: str) -> None:
    """Remove the user's memory entirely (guest cleanup)."""
    clear(user)
    try:
        _dir(user).rmdir()
    except OSError:
        pass
    (_DIR / f"{_dir(user).name}.md").unlink(missing_ok=True)


def rename_user(old: str, new: str) -> None:
    """Carry the memory across an account rename (directory or legacy file)."""
    if _dir(old).exists():
        _dir(old).replace(_dir(new))
    legacy = _DIR / f"{_dir(old).name}.md"
    if legacy.exists():
        legacy.replace(_DIR / f"{_dir(new).name}.md")
