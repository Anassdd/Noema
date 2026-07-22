"""LLM-driven memory EVOLUTION — the automatic counterpart to /remember and /note.

The design mirrors the frontier products (verified against the real Claude.ai and
ChatGPT memory UIs): the profile is a TOPICAL document — `## Topic` sections of
connected prose — and the judge's unit of change is the whole section: new
information is woven INTO the paragraph it belongs to, never appended as another
loose line. The time-bound "now" file stays a dated list (each item needs its own
expiry), evolved through exact-match line operations. Everything that stops being
true is archived to history — the bi-temporal retire-don't-delete rule — so
nothing the memory knew is silently lost.

Two deliberate adaptations to Noema's scale:
- The WHOLE live memory rides in the judge's context instead of a vector-similarity
  pre-selection. Mem0 needs retrieval because its stores hold thousands of
  memories; a capped per-user document doesn't — and skipping embeddings keeps
  personal facts out of the vector stores entirely.
- Domain OPINIONS the user asserts are routed to the per-context beliefs file, not
  the profile: Noema keeps "what the user is like" (memory) and "what the user
  thinks about the domain" (beliefs, contrasted against sources) apart by design.

All model access goes through llm_client, so this stays provider-agnostic.
"""

from __future__ import annotations

import json
import re

from app import llm_client

_SYSTEM = """You maintain the user's long-term memory across chats. It has three parts:

- profile — a topical document about the user: `## Topic (updated)` sections
  (e.g. Identity, Work, Preferences, Projects…), each a short paragraph of
  connected prose. THE SECTION IS YOUR UNIT OF CHANGE: to record something
  durable, rewrite the whole section it belongs to, weaving the new information
  into the existing sentences (or open a new section when no topic fits).
- now — the user's CURRENT, time-bound situation as dated one-line facts,
  ideally with an end date ("in Paris until Sept 1", "preparing an exam in March").
- history (never edited directly) — the archive; reached via "retire"/"archive".

You receive the profile, the now list, today's date, and the latest exchange.
Reply with OPERATIONS — never a full new memory.

Operations:
- {"op": "profile", "section": "<topic title>", "text": "<the FULL rewritten
   section — flowing prose, no bullets, no headings inside; empty string
   removes the section>"}
- {"op": "archive", "text": "<past-tense sentence>"} whenever a profile rewrite
  drops something that WAS true (an ended era, a changed role) — it must land in
  history, never just vanish.
- {"op": "add", "fact": "<new fact>", "until": "YYYY-MM-DD"?} for a new
  time-bound fact in now.
- {"op": "update", "replaces": "<exact existing now-fact>", "fact": "<revised>",
   "until": "YYYY-MM-DD"?} when the exchange refines or supersedes a now-fact.
- {"op": "delete", "fact": "<exact existing now-fact>"} only when a now-fact was
  wrong from the start and nothing replaces it.
- {"op": "retire", "fact": "<exact existing now-fact>", "as": "<the same fact in
   past tense>"} when something STOPPED being true (a stay ended) — it moves to
  history. When a temporary now-fact proves durable, retire it AND weave it into
  the right profile section.

"until": resolve stated ends ("till September", "until the 1st") to a concrete
date using today's date; omit when no end is stated. Quote "replaces"/"fact"
targets exactly as written WITHOUT the trailing date parentheses. Keep section
titles short (1–3 words).

STYLE — compact notes, the user is the implicit subject: "Name: Anas Said.",
"Interning at BNP Paribas, building Noema.", "In Paris until 2026-09-01.",
"Prefers concise answers." NEVER write "The user is/has…" (wasted space on
every line) and never address the user as "you".

Write in the language the user's messages are WRITTEN in — judged by the words
themselves, NEVER by the user's name, origin or topic (a user named Anas writing
in English gets English text; someone writing in French gets French). If unclear,
use English. When rewriting an existing section or fact, keep its language.

Separately, "beliefs": OPINIONS or stances the user asserts about the DOMAIN under
discussion ("I think X is overrated", "in my view the limit should be 3%") — their
view, not a personal fact and not established knowledge. You receive the CURRENT
notes; each belief is {"note": "<short standalone note keeping the user's exact
claim and language>", "replaces": "<the exact existing note it refines or
REVERSES, without its date parentheses>" or null} — "actually X is fine" must
replace the old "X is overrated" note, never pile up next to it.

CRITICAL — only trust the USER. Record ONLY what the user explicitly stated or
confirmed. NEVER record what the assistant guessed, asked, assumed, or suggested.
Do NOT record: one-off questions, transient task details, general knowledge, facts
about the assistant, or anything already covered by the current memory (omit —
there is no noop operation). When nothing qualifies, return empty lists.

Respond with ONLY JSON: {"operations": [...], "beliefs": ["..."]}. No prose."""

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Trailing date-paren a target may carry even though the judge is told to omit it.
_META = re.compile(r"\s*\((\d{4}-\d{2}-\d{2})(?:\s*→\s*(\d{4}-\d{2}-\d{2}))?\)\s*$")


def evolve(messages: list[dict], profile: str, now_lines: list[str],
           today: str, notes: list[str] | None = None) -> dict:
    """Judge the latest exchange against the live memory. Returns validated
    operations {"profile": [(title, text)], "archive": [...],
    "add": [(fact, until)], "update": [(old, new, until)], "delete": [old],
    "retire": [(old, as_text)], "beliefs": [(note, replaces|None)]} — targets
    that don't match a current fact/note are downgraded (update -> add) or
    dropped, so a hallucinated target can never destroy a real memory."""
    transcript = "\n".join(
        f"{m['role']}: {m['content']}" for m in messages if m.get("content")
    )
    empty = {"profile": [], "archive": [], "add": [], "update": [], "delete": [],
             "retire": [], "beliefs": []}
    if not transcript.strip():
        return empty

    user = (
        f"Today: {today}\n\n"
        f"profile:\n{profile.strip() or '(empty)'}\n\n"
        f"now:\n" + ("\n".join(now_lines) or "(empty)") + "\n\n"
        f"notes (beliefs about the domain):\n" + ("\n".join(notes or []) or "(empty)") + "\n\n"
        f"Latest exchange:\n{transcript}\n\n"
        "Return the operations (and any asserted beliefs)."
    )
    result = llm_client.chat(
        [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
        stream=False,
        temperature=0,
    )
    return _parse_operations(result.text, now_lines, notes or [])


def place_fact(fact: str, profile: str, today: str) -> tuple[str, str] | None:
    """/remember's placement: weave one user-stated fact into the profile's best
    section (or a new one). Returns (section title, full rewritten section), or
    None (caller falls back to a plain Notes append)."""
    system = (
        "You maintain a user profile made of `## Topic` sections of connected "
        "prose. Weave the given fact into the section it belongs to — rewrite "
        "that section's FULL text — or open a new, short-titled section when no "
        "topic fits. Never drop existing information; never invent. Compact-note "
        'style, the user as implicit subject ("Prefers concise answers."), never '
        '"The user is…". Respond with '
        'ONLY JSON: {"section": "<title>", "text": "<full section text>"}.'
    )
    result = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": f"profile:\n{profile.strip() or '(empty)'}\n\nfact: {fact}"}],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    if not isinstance(data, dict):
        return None
    title = _strip(str(data.get("section") or ""))
    text = str(data.get("text") or "").strip()
    return (title, text) if title and text else None


def consolidate_profile(text: str, cap: int, today: str) -> dict | None:
    """Compact the profile document under its cap: merge overlapping sections,
    tighten prose, keep the `## Topic (date)` structure, and move dropped-but-
    true details to "archive" as past-tense sentences rather than losing them.
    Returns {"text": ..., "archive": [...]}, or None when the reply fails
    validation (caller keeps the original)."""
    system = (
        f"You compact a user-profile document to fit under {cap} characters. "
        "Merge sections that overlap, tighten the prose, keep the `## Topic "
        "(YYYY-MM-DD)` heading structure and each heading's date, and NEVER "
        "invent anything new. Details that no longer earn their space but WERE "
        f"true go to \"archive\" as past-tense sentences ending with ({today}). "
        'Respond with ONLY JSON: {"text": "<the compacted document>", '
        '"archive": ["..."]}.'
    )
    result = llm_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    if not isinstance(data, dict):
        return None
    compacted = str(data.get("text") or "").strip()
    archive = [a.strip() for a in data.get("archive") or []
               if isinstance(a, str) and a.strip()]
    if not compacted or len(compacted) >= len(text.strip()):
        return None
    if "## " in text and "## " not in compacted:
        return None
    return {"text": compacted, "archive": archive}


def consolidate_now(lines: list[str], cap: int, today: str) -> dict | None:
    """Compact now.md's dated fact lines under the cap: merge overlap, tighten,
    RETIRE the least important to history rather than dropping information.
    Returns {"facts": [...], "retire": [...]} (full `fact (dates)` strings), or
    None when the reply fails validation."""
    system = (
        f'You compact the "now" list of a user\'s memory to fit under {cap} '
        "characters. Merge facts that say overlapping things, tighten wording, "
        "keep every distinct piece of information you can, and NEVER invent. "
        "Each fact keeps its trailing date parentheses (a merged fact keeps the "
        "most recent dates). If it still cannot fit, RETIRE the least important "
        "facts: rewrite each in past tense, replacing its parentheses with "
        f'"(<learned date> → {today})", and return those under "retire" instead '
        'of dropping them. Respond with ONLY JSON: '
        '{"facts": ["..."], "retire": ["..."]}.'
    )
    result = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": "\n".join(lines)}],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    if not isinstance(data, dict):
        return None
    kept = [f.strip() for f in data.get("facts") or [] if isinstance(f, str) and f.strip()]
    retired = [f.strip() for f in data.get("retire") or [] if isinstance(f, str) and f.strip()]
    if len(kept) + len(retired) == 0 or len(kept) + len(retired) > len(lines):
        return None
    if sum(map(len, kept)) >= sum(map(len, lines)) and not retired:
        return None
    return {"facts": kept, "retire": retired}


def summarize_chats(convs: list[dict]) -> list[str] | None:
    """One compact journal line per conversation ({"title", "messages"}), in
    order — the lazy daily pass. None on a bad reply (the pass just skips)."""
    blocks = []
    for i, conv in enumerate(convs):
        turns = "\n".join(
            f"{m.get('role')}: {str(m.get('content'))[:400]}"
            for m in conv["messages"][-12:] if m.get("content"))
        blocks.append(f"[{i + 1}] title: {conv.get('title') or '(untitled)'}\n{turns}")
    system = (
        "You write a user's chat journal. For EACH numbered conversation return "
        "ONE compact line (under ~140 chars) capturing what was discussed, asked "
        "or decided — telegraphic style, no subject fluff, keep the "
        "conversation's language. Respond with ONLY JSON: "
        '{"lines": ["..."]} in the same order.'
    )
    result = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": "\n\n".join(blocks)}],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    lines = data.get("lines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or len(lines) != len(convs):
        return None
    cleaned = [" ".join(l.split()) for l in lines if isinstance(l, str) and l.strip()]
    return cleaned if len(cleaned) == len(convs) else None


def compact_journal(text: str, target: int) -> str | None:
    """Shrink an overgrown journal: recent entries stay verbatim, the oldest
    merge into per-month digest lines. None on a bad reply (keep the original)."""
    system = (
        f"You compact a chat journal (one dated line per entry, newest last) to "
        f"under {target} characters. Keep the MOST RECENT entries verbatim and "
        "merge the oldest into one digest line per month, formatted "
        "'YYYY-MM · digest…'. Never invent. Respond with ONLY JSON: "
        '{"text": "<the compacted journal>"}.'
    )
    result = llm_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    compacted = str(data.get("text") or "").strip() if isinstance(data, dict) else ""
    if not compacted or len(compacted) >= len(text.strip()):
        return None
    return compacted


def consolidate_notes(lines: list[str], cap: int) -> list[str] | None:
    """Compact a context's belief notes under the cap: merge notes that say
    overlapping things, keep each note's language and its date parentheses
    (a merged note keeps the most recent date), NEVER invent or soften the
    user's claims. Returns the new lines, or None (caller keeps the original —
    a belief must never be lost to a bad model day)."""
    system = (
        f"You compact a user's list of opinion notes to fit under {cap} "
        "characters. Merge notes that assert overlapping things, keep every "
        "distinct stance, keep each note's language and trailing date "
        "parentheses (a merged note keeps the most recent date), and NEVER "
        "invent or soften a claim. Respond with ONLY JSON: "
        '{"notes": ["..."]}.'
    )
    result = llm_client.chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": "\n".join(lines)}],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    kept = data.get("notes") if isinstance(data, dict) else None
    if not isinstance(kept, list):
        return None
    cleaned = [n.strip() for n in kept if isinstance(n, str) and n.strip()]
    if not cleaned or len(cleaned) > len(lines):
        return None
    if sum(map(len, cleaned)) >= sum(map(len, lines)):
        return None
    return cleaned


def expand_query(question: str) -> list[str]:
    """The paraphrase/language bridge for archive recall — fired ONLY when an
    explicitly past-referential question found nothing lexically. Returns a
    handful of alternative single-word keywords (synonyms, French/English
    translations, likely proper names), or [] — recall just stays empty then."""
    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "A question about the user's own past found no keyword match in "
                    "their memory archive. Give up to 8 alternative SINGLE-WORD "
                    "search keywords: synonyms, the French and English translations "
                    "of the key terms, and likely proper names (e.g. 'the Turkish "
                    "trip' → istanbul, turquie, turkey, voyage). Respond with ONLY "
                    'JSON: {"keywords": ["..."]}.'
                ),
            },
            {"role": "user", "content": question},
        ],
        stream=False,
        temperature=0,
        max_tokens=100,
    )
    data = _loads_lenient(result.text)
    words = data.get("keywords") if isinstance(data, dict) else None
    if not isinstance(words, list):
        return []
    return [w.strip() for w in words if isinstance(w, str) and w.strip()][:8]


def rewrite_past(facts: list[str]) -> list[str] | None:
    """Past-tense rewrites for the expiry sweep ("is in Paris" -> "was in Paris").
    Returns one rewrite per fact in order, or None (caller retires verbatim)."""
    numbered = "\n".join(f"{i + 1}. {f}" for i, f in enumerate(facts))
    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "Rewrite each numbered fact about a user in the past tense — the "
                    "period it describes has ended. Keep each fact's language and "
                    "every detail; change ONLY the tense. Respond with ONLY JSON: "
                    '{"rewritten": ["..."]} in the same order.'
                ),
            },
            {"role": "user", "content": numbered},
        ],
        stream=False,
        temperature=0,
    )
    data = _loads_lenient(result.text)
    out = data.get("rewritten") if isinstance(data, dict) else None
    if not isinstance(out, list) or len(out) != len(facts):
        return None
    cleaned = [f.strip() for f in out if isinstance(f, str) and f.strip()]
    return cleaned if len(cleaned) == len(facts) else None


def _strip(text: str) -> str:
    return _META.sub("", (text or "").strip().lstrip("#").strip()).strip()


def _parse_operations(text: str, now_lines: list[str],
                      notes: list[str] | None = None) -> dict:
    out = {"profile": [], "archive": [], "add": [], "update": [], "delete": [],
           "retire": [], "beliefs": []}
    data = _loads_lenient(text)
    if not isinstance(data, dict):
        return out

    known = {}
    for line in now_lines:
        fact = _strip(line.lstrip("- "))
        if fact:
            known[fact.lower()] = fact
    seen = set(known)

    def valid_until(op: dict) -> str | None:
        until = (op.get("until") or "").strip()
        return until if _DATE.match(until) else None

    ops = data.get("operations")
    for op in ops if isinstance(ops, list) else []:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")

        if kind == "profile":
            title = _strip(str(op.get("section") or ""))
            if title:
                out["profile"].append((title, str(op.get("text") or "")))
            continue
        if kind == "archive":
            note = " ".join(str(op.get("text") or "").split())
            if note:
                out["archive"].append(note)
            continue

        fact = _strip(op.get("fact") or "")
        if not fact:
            continue
        if kind == "update":
            target = known.get(_strip(op.get("replaces") or "").lower())
            if target:
                out["update"].append((target, fact, valid_until(op)))
                seen.add(fact.lower())
            elif fact.lower() not in seen:  # unknown target -> the info is still new
                out["add"].append((fact, valid_until(op)))
                seen.add(fact.lower())
        elif kind == "delete":
            target = known.get(fact.lower())
            if target:
                out["delete"].append(target)
        elif kind == "retire":
            target = known.get(fact.lower())
            if target:
                out["retire"].append((target, _strip(op.get("as") or "") or target))
        elif kind == "add":
            if fact.lower() not in seen:
                out["add"].append((fact, valid_until(op)))
                seen.add(fact.lower())

    # Beliefs: {"note", "replaces"} objects (bare strings tolerated). A replaces
    # target that isn't a current note is defused to a plain add.
    known_notes = {_strip(n).lower(): _strip(n) for n in (notes or [])}
    raw = data.get("beliefs", [])
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            note, replaces = entry, None
        elif isinstance(entry, dict):
            note = str(entry.get("note") or "")
            replaces = known_notes.get(_strip(str(entry.get("replaces") or "")).lower())
        else:
            continue
        note = " ".join(note.split())
        if note:
            out["beliefs"].append((note, replaces))
    return out


def _loads_lenient(text: str):
    """Parse JSON even if the model wrapped it in prose or code fences."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start: end + 1])
            except json.JSONDecodeError:
                return None
        return None
