"""Persistent user-fact memory: the three-file store (profile / now / history)
evolved by /remember (manual) and the LLM judge (/memory/auto). This is distinct
from the document/graph memory — it stores durable facts about the *user*, not
document knowledge. Scoped to the signed-in account.

Every endpoint returns the same state payload (facts, injection context, files,
gauges) so the frontend never needs a second round-trip after a change.
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app import beliefs, conversation_store, memory_judge, memory_store
from app.routers.auth import require_user
from app.schemas import ChatRequest, MemoryMarkdown, MemoryRequest

router = APIRouter(prefix="/memory")


def _state(username: str) -> dict:
    return {
        "memories": memory_store.live_facts(username),
        "context": memory_store.context_block(username),
        "files": memory_store.load_files(username),
        "usage": memory_store.usage(username),
    }


def _sweep_if_due(username: str) -> list[str]:
    """The lazy session-start expiry pass: once a day, retire now-facts whose
    until-date has passed — past-tense via the LLM when it cooperates, verbatim
    otherwise (the sweep must never be blocked by a bad model day)."""
    today = date.today().isoformat()
    if not memory_store.sweep_due(username, today):
        return []
    expired = memory_store.expired(username, today)
    retired: list[str] = []
    if expired:
        texts = [fact for fact, _learned, _until in expired]
        rewrites = memory_judge.rewrite_past(texts) or texts
        retired = memory_store.retire_facts(username, list(zip(texts, rewrites)))
    memory_store.mark_swept(username, today)
    return retired


_JOURNAL_BATCH = 8
# Per-session cadence with a floor: same-day continuity ("what did we discuss
# this morning?" from another chat) without re-running on every reload.
_JOURNAL_EVERY = timedelta(minutes=30)


def _journal_if_due(user: dict) -> None:
    """The lazy journal pass: summarize conversations that changed since the
    last pass into one dated line each (a single batched LLM call), then
    compact the journal when it outgrows its budget. A bad model day skips a
    pass — never blocks the session.

    When more conversations changed than one batch covers, the stamp only
    advances to the last one processed — the next load continues the catch-up
    instead of silently dropping the rest."""
    username = user["username"]
    since = memory_store.journal_stamp(username)
    try:
        last = datetime.fromisoformat(since) if since else None
    except ValueError:
        last = None
    if last and datetime.now(timezone.utc) - last < _JOURNAL_EVERY:
        return
    changed = sorted(
        (c for c in conversation_store.list_summaries(
            username, user.get("is_guest", False)) if c["updated_at"] > since),
        key=lambda c: c["updated_at"])
    batch = changed[:_JOURNAL_BATCH]
    convs = []
    for summary in batch:
        conv = conversation_store.get(summary["id"], username,
                                      user.get("is_guest", False))
        if conv and len(conv["messages"]) >= 2:
            convs.append(conv)
    if convs:
        lines = memory_judge.summarize_chats(convs)
        if lines:
            memory_store.append_journal(
                username,
                [f"{conv['updated_at'][:10]} · {conv['title'] or 'Untitled'} — {line}"
                 for conv, line in zip(convs, lines)],
                sources=[conv["id"] for conv in convs])
    journal = memory_store.load_file(username, "journal")
    if len(journal) > memory_store.JOURNAL_COMPACT_AT:
        compacted = memory_judge.compact_journal(
            journal, memory_store.JOURNAL_COMPACT_AT // 2)
        if compacted:
            memory_store.save_file(username, "journal", compacted)
            memory_store.prune_journal_index(username)
    memory_store.mark_journal(
        username,
        batch[-1]["updated_at"] if len(changed) > len(batch)
        else datetime.now(timezone.utc).isoformat())


# One journal pass per user at a time — two tabs mounting together must not
# double-summarize.
_journal_running: set[str] = set()
_journal_lock = threading.Lock()


def _spawn_journal(user: dict) -> None:
    """Run the journal pass on a daemon thread: it can take seconds (a batched
    LLM call), and nothing in the CURRENT response depends on it — its lines
    matter for the NEXT conversation's context."""
    username = user["username"]
    with _journal_lock:
        if username in _journal_running:
            return
        _journal_running.add(username)

    def run() -> None:
        try:
            _journal_if_due(user)
        finally:
            with _journal_lock:
                _journal_running.discard(username)

    threading.Thread(target=run, daemon=True).start()


@router.get("")
def get_memory(user: dict = Depends(require_user)) -> dict:
    """The full memory state. Loading it (app mount = session start) also runs
    the expiry sweep — 'in Paris until Sept 1' stops being current the day
    after, moved to history, not erased — and kicks off the journal pass in
    the background. The sweep stays synchronous: its no-expiry fast path is a
    regex scan, and when something DID expire it must leave the context before
    this session's first message."""
    retired = _sweep_if_due(user["username"])
    _spawn_journal(user)
    return {**_state(user["username"]), "expired": retired}




@router.put("/files/{name}")
def put_file(name: str, req: MemoryMarkdown, user: dict = Depends(require_user)) -> dict:
    """Overwrite one memory file with the user's edit (the settings editor)."""
    if name not in memory_store.FILES:
        raise HTTPException(status_code=404, detail=f"No memory file '{name}'")
    memory_store.save_file(user["username"], name, req.markdown)
    return _state(user["username"])


@router.post("")
def add_memory(req: MemoryRequest, user: dict = Depends(require_user)) -> dict:
    """Persist a fact (/remember): woven into the profile's best topic section
    by the placement judge, or appended to a Notes section when the model
    doesn't cooperate — the save itself must never fail."""
    username = user["username"]
    today = date.today().isoformat()
    placed = memory_judge.place_fact(
        req.fact, memory_store.load_file(username, "profile"), today)
    if placed:
        memory_store.write_section(username, placed[0], placed[1], today)
    else:
        notes = memory_store.section_body(username, "Notes")
        memory_store.write_section(
            username, "Notes",
            (notes + "\n" if notes else "") + req.fact.strip(), today)
    return _state(username)


@router.post("/remove")
def remove_memory(req: MemoryRequest, user: dict = Depends(require_user)) -> dict:
    """Remove one now-fact (/forget) — or a whole profile topic by its title."""
    memory_store.remove_fact(user["username"], req.fact)
    return _state(user["username"])


@router.delete("")
def clear_memory(user: dict = Depends(require_user)) -> dict:
    """Clear the whole memory — profile, now AND history."""
    memory_store.clear(user["username"])
    return _state(user["username"])


@router.post("/auto")
def auto_memory(req: ChatRequest, user: dict = Depends(require_user)) -> dict:
    """Automatic memory EVOLUTION from the latest exchange — no explicit command.

    The judge rewrites the profile topic sections the exchange touches (weaving,
    not appending), evolves the dated now-list through exact-match operations,
    archives anything that stopped being true, and routes asserted domain
    opinions into the beliefs file of the memory context this chat answers from
    (req.domain / req.memory). A live file past its cap then gets a
    consolidation pass — merge, tighten, retire — never silent loss. The
    response spells out what changed so the UI can confirm it inline."""
    username = user["username"]
    today = date.today().isoformat()
    ops = memory_judge.evolve(
        [m.model_dump() for m in req.messages],
        memory_store.load_file(username, "profile"),
        memory_store.fact_lines(username, "now"),
        today,
        beliefs.notes(req.domain, req.memory, username))

    for title, text in ops["profile"]:
        memory_store.write_section(username, title, text, today)
    memory_store.append_history(
        username, [f"{note} ({today})" for note in ops["archive"]])
    done = memory_store.apply_now_operations(username, ops, today)

    noted = beliefs.apply_note_operations(
        ops["beliefs"], req.domain, req.memory, username, today)
    if len(beliefs.read_beliefs(req.domain, req.memory, username)) > beliefs.MAX_CHARS:
        merged = memory_judge.consolidate_notes(
            beliefs.note_lines(req.domain, req.memory, username), beliefs.MAX_CHARS)
        if merged is not None:
            beliefs.replace_notes(merged, req.domain, req.memory, username)

    consolidated = False
    profile_text = memory_store.load_file(username, "profile")
    if len(profile_text) > memory_store.CAPS["profile"]:
        result = memory_judge.consolidate_profile(
            profile_text, memory_store.CAPS["profile"], today)
        if result is not None:
            memory_store.save_file(username, "profile", result["text"])
            memory_store.append_history(username, result["archive"])
            consolidated = True
    if len(memory_store.load_file(username, "now")) > memory_store.CAPS["now"]:
        result = memory_judge.consolidate_now(
            memory_store.fact_lines(username, "now"),
            memory_store.CAPS["now"], today)
        if result is not None:
            memory_store.replace_now(username, result["facts"])
            memory_store.append_history(
                username, [r.lstrip("- ").strip() for r in result["retire"]])
            consolidated = True

    return {
        **done,
        "profile_updated": [title for title, _ in ops["profile"]],
        "archived": ops["archive"],
        "beliefs_added": noted["added"],
        "beliefs_updated": noted["updated"],
        "consolidated": consolidated,
        **_state(username),
    }
