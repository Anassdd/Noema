"""Three-file memory tests (topical profile + dated now + history) — no network:

    backend/.venv/bin/python tests/test_memory_evolution.py

The judge's LLM call is stubbed with canned JSON; state goes to a scratch dir.
Covers: operation parsing (profile section rewrites, archives, and the safety
downgrades — a hallucinated now-update target becomes an add, hallucinated
delete/retire are dropped), section write/rewrite/remove with updated-dates,
now-file application (retire → history with date range), the expiry sweep,
cap-driven consolidation validation for both file shapes, /remember placement
with its Notes fallback, the legacy single-file migration, and the /auto route
wiring beliefs into the current memory context.
"""

import os
import sys
import tempfile
from pathlib import Path

_SCRATCH = tempfile.mkdtemp(prefix="noema-memevo-test-")
os.environ["NOEMA_STATE_DIR"] = _SCRATCH
os.environ.setdefault("OPENAI_API_KEY", "test-key-never-called")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import json  # noqa: E402

from app import beliefs, memory_judge, memory_store  # noqa: E402

TODAY = "2026-07-22"


class _CannedLLM:
    """Stands in for llm_client: returns queued replies, records prompts."""

    def __init__(self):
        self.replies: list[str] = []
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        text = self.replies.pop(0) if self.replies else "{}"
        return type("R", (), {"text": text, "usage": None, "model": "stub"})()


_LLM = _CannedLLM()
memory_judge.llm_client = _LLM


def test_operations_parse_and_validate():
    now_lines = ["The user is preparing an exam. (2026-06-01)"]
    _LLM.replies = [json.dumps({
        "operations": [
            {"op": "profile", "section": "Work",
             "text": "The user is an intern at BNP Paribas, building Noema."},
            {"op": "archive", "text": "The user studied at Sorbonne until 2026."},
            {"op": "add", "fact": "The user is in Paris for an internship.",
             "until": "2026-09-01"},
            {"op": "add", "fact": "The user is fasting.", "until": "someday"},  # bad date
            {"op": "update", "replaces": "The user drives a Ferrari.",  # hallucinated
             "fact": "The user cycles to work."},
            {"op": "delete", "fact": "The user owns a boat."},           # hallucinated
            {"op": "retire", "fact": "the user is preparing an exam. (2026-06-01)",
             "as": "The user prepared an exam."},   # case + date-paren tolerant
        ],
        "beliefs": ["Basel III output floors are too strict."],
    })]
    ops = memory_judge.evolve([{"role": "user", "content": "hi"}],
                              "", now_lines, TODAY)
    assert ops["profile"] == [("Work",
                               "The user is an intern at BNP Paribas, building Noema.")]
    assert ops["archive"] == ["The user studied at Sorbonne until 2026."]
    assert ("The user is in Paris for an internship.", "2026-09-01") in ops["add"]
    assert ("The user is fasting.", None) in ops["add"], \
        "an invalid until-date is dropped, the fact kept"
    assert ("The user cycles to work.", None) in ops["add"], \
        "an update with an unknown target must downgrade to add, never vanish"
    assert ops["delete"] == [], "a hallucinated delete target is dropped"
    assert ops["retire"] == [("The user is preparing an exam.",
                              "The user prepared an exam.")]
    assert ops["beliefs"] == [("Basel III output floors are too strict.", None)], \
        "bare-string beliefs are tolerated and parse as plain adds"
    print("  operation parsing: sections + archives kept, hallucinated targets defused ✓")


def test_profile_sections():
    user = "evo-sections"
    memory_store.clear(user)
    memory_store.write_section(user, "Identity",
                               "The user's name is Anas.", "2026-06-01")
    memory_store.write_section(user, "Work",
                               "The user is an intern at BNP.", "2026-06-01")
    assert memory_store.section_titles(user) == ["Identity", "Work"]

    # A rewrite weaves new info in, keeps position, refreshes the date.
    memory_store.write_section(
        user, "Work",
        "The user is an intern at BNP Paribas in Paris, building Noema.", TODAY)
    md = memory_store.load_file(user, "profile")
    assert f"## Work ({TODAY})" in md and "## Identity (2026-06-01)" in md
    assert memory_store.section_titles(user) == ["Identity", "Work"], \
        "a rewritten section keeps its position"
    assert "building Noema" in memory_store.section_body(user, "work")

    # Stray headings in model text are defused; empty text removes the section.
    memory_store.write_section(user, "Junk", "## sneaky\nreal text", TODAY)
    assert memory_store.section_titles(user) == ["Identity", "Work", "Junk"]
    assert "sneaky" in memory_store.section_body(user, "Junk")
    memory_store.write_section(user, "Junk", "", TODAY)
    assert memory_store.section_titles(user) == ["Identity", "Work"]

    # The user's own preamble prose survives every operation.
    memory_store.save_file(user, "profile",
                           "My own intro.\n\n" + memory_store.load_file(user, "profile"))
    memory_store.write_section(user, "Identity", "The user is called Anas.", TODAY)
    assert memory_store.load_file(user, "profile").startswith("My own intro."), \
        "preamble text must survive section rewrites"
    print("  profile sections: weave-in-place, dates, defused headings, preamble ✓")


def test_apply_now_operations():
    user = "evo-now"
    memory_store.clear(user)
    memory_store.add_fact(user, "The user is learning Rust.", "2026-06-01")
    memory_store.add_fact(user, "The user is in Paris for an internship.",
                          "2026-06-01", "2026-09-01")
    done = memory_store.apply_now_operations(user, {
        "update": [("The user is learning Rust.",
                    "The user is learning Rust and Go.", None)],
        "retire": [("The user is in Paris for an internship.",
                    "The user was in Paris for an internship.")],
        "add": [("The user is learning Rust and Go.", None),   # dup ignored
                ("The user is preparing a talk.", "2026-08-01")],
    }, TODAY)
    assert memory_store.facts(user, "now") == \
        ["The user is learning Rust and Go.", "The user is preparing a talk."]
    assert "The user was in Paris for an internship. (2026-06-01 → 2026-07-22)" \
        in memory_store.load_file(user, "history"), \
        "retire must carry the original learned date into history"
    lines = memory_store.fact_lines(user, "now")
    assert lines[0].endswith(f"({TODAY})") and lines[1].endswith(f"({TODAY} → 2026-08-01)")
    assert done == {"added": ["The user is preparing a talk."],
                    "updated": ["The user is learning Rust and Go."],
                    "removed": [],
                    "retired": ["The user was in Paris for an internship."]}
    print("  now ops: update in place, retire → history with range, dedup add ✓")


def test_expiry_sweep():
    user = "evo-sweep"
    memory_store.clear(user)
    memory_store.add_fact(user, "The user is in Paris for an internship.",
                          "2026-06-01", "2026-07-01")
    memory_store.add_fact(user, "The user is preparing a talk.",
                          "2026-06-01", "2026-12-01")
    memory_store.add_fact(user, "The user is learning Rust.", "2026-06-01")
    expired = memory_store.expired(user, TODAY)
    assert [(f, u) for f, _l, u in expired] == \
        [("The user is in Paris for an internship.", "2026-07-01")], \
        "only past until-dates expire; dateless facts never do"

    retired = memory_store.retire_facts(
        user, [("The user is in Paris for an internship.",
                "The user was in Paris for an internship.")])
    assert retired == ["The user was in Paris for an internship."]
    assert memory_store.facts(user, "now") == \
        ["The user is preparing a talk.", "The user is learning Rust."]
    assert "The user was in Paris for an internship. (2026-06-01 → 2026-07-01)" \
        in memory_store.load_file(user, "history"), \
        "an expired fact's range must end at its until-date, not the sweep day"

    assert memory_store.sweep_due(user, TODAY)
    memory_store.mark_swept(user, TODAY)
    assert not memory_store.sweep_due(user, TODAY)
    assert memory_store.sweep_due(user, "2026-07-23")
    print("  sweep: expiry detection, retirement range, once-a-day stamp ✓")


def test_consolidation_never_loses_memory():
    profile = ("## Work (2026-06-01)\nThe user is an intern at BNP Paribas.\n\n"
               "## Job (2026-06-02)\nThe user interns at BNP.\n")
    _LLM.replies = [json.dumps({
        "text": "## Work (2026-06-02)\nThe user is an intern at BNP Paribas.",
        "archive": ["The user's Job section merged into Work. (2026-07-22)"],
    })]
    result = memory_judge.consolidate_profile(profile, 100, TODAY)
    assert result and "## Work" in result["text"] and len(result["archive"]) == 1
    _LLM.replies = ["not json"]
    assert memory_judge.consolidate_profile(profile, 100, TODAY) is None
    _LLM.replies = [json.dumps({"text": profile + "invented extra", "archive": []})]
    assert memory_judge.consolidate_profile(profile, 100, TODAY) is None, \
        "a GROWING 'compaction' is suspect"
    _LLM.replies = [json.dumps({"text": "prose with no sections", "archive": []})]
    assert memory_judge.consolidate_profile(profile, 100, TODAY) is None, \
        "a compaction that loses the section structure is suspect"

    lines = [f"The user fact {i}. (2026-06-01)" for i in range(10)]
    _LLM.replies = [json.dumps({
        "facts": ["The user facts 0-8 merged. (2026-06-01)"],
        "retire": ["The user did fact 9. (2026-06-01 → 2026-07-22)"],
    })]
    assert memory_judge.consolidate_now(lines, 300, TODAY) == {
        "facts": ["The user facts 0-8 merged. (2026-06-01)"],
        "retire": ["The user did fact 9. (2026-06-01 → 2026-07-22)"]}
    _LLM.replies = [json.dumps({"facts": [], "retire": []})]
    assert memory_judge.consolidate_now(lines, 300, TODAY) is None, \
        "an empty reply must never wipe"
    print("  consolidation: only genuine compactions accepted, both shapes ✓")


def test_remember_placement_and_fallback():
    from app.routers import memory as memory_router
    from app.schemas import MemoryRequest

    user = {"username": "evo-place", "is_guest": False, "is_admin": False}
    memory_store.clear(user["username"])
    memory_store.mark_swept(user["username"], "9999-01-01")

    _LLM.replies = [json.dumps({
        "section": "Preferences",
        "text": "The user prefers concise answers.",
    })]
    res = memory_router.add_memory(MemoryRequest(fact="I prefer concise answers"),
                                   user=user)
    assert "Preferences" in memory_store.section_titles(user["username"])
    assert "The user prefers concise answers." in res["context"]

    _LLM.replies = ["garbage"]
    memory_router.add_memory(MemoryRequest(fact="likes chess"), user=user)
    assert "likes chess" in memory_store.section_body(user["username"], "Notes"), \
        "a failed placement must still save the fact (Notes fallback)"
    print("  /remember: woven into the right section, Notes fallback on failure ✓")


def test_journal_tail_and_recall():
    user = "evo-journal"
    memory_store.clear(user)
    memory_store.append_journal(user, [
        "2026-07-20 · Basel questions — asked about output floors and CVA.",
        "2026-07-21 · Trip planning — compared Istanbul and Sofia for a weekend.",
        "2026-07-22 · Bench — discussed judge decoupling and run cost.",
    ])
    memory_store.append_history(
        user, ["Was in Istanbul for a conference. (2026-05-02 → 2026-05-09)"])

    ctx = memory_store.context_block(user)
    assert "## Recent chats" in ctx and "judge decoupling" in ctx, \
        "the journal tail must ride in the injection block"
    assert "conference" not in ctx, "history must never ride in the block"

    hits = memory_store.recall(user, "when was I in Istanbul?")
    assert any("conference" in h for h in hits) and \
        any("Sofia" in h for h in hits), \
        "recall must reach BOTH archive tiers WITHOUT any regex gate"
    assert memory_store.recall(user, "the and was") == [], \
        "stopword-only queries must return nothing"
    assert memory_store.recall(user, "quantum entanglement lasers") == [], \
        "topics the archive never saw must inject nothing"
    wide = memory_store.recall(user, "what did we say about istanbul", wide=True)
    assert len(wide) >= len(hits), "wide mode may only loosen the bar"

    # Tail budget: many long lines -> only the newest that fit are injected.
    memory_store.append_journal(
        user, [f"2026-07-2{i} · Filler — {'x' * 200}." for i in range(3)])
    tail = memory_store.journal_tail(user)
    assert sum(map(len, tail)) <= memory_store.JOURNAL_TAIL_CHARS + 220
    assert tail[-1].startswith("2026-07-22 · Filler"), "tail keeps the newest"
    print("  journal: tail injected within budget, recall spans both archives ✓")


def test_journal_daily_pass():
    from app.routers import memory as memory_router

    user = {"username": "evo-journal2", "is_guest": False, "is_admin": False}
    memory_store.clear(user["username"])

    class _Convs:
        @staticmethod
        def list_summaries(username, is_guest):
            return [{"id": "c1", "title": "Basel chat",
                     "updated_at": "2026-07-21T10:00:00+00:00"}]

        @staticmethod
        def get(cid, username, is_guest):
            return {"id": cid, "title": "Basel chat",
                    "updated_at": "2026-07-21T10:00:00+00:00",
                    "messages": [{"role": "user", "content": "explain CVA"},
                                 {"role": "assistant", "content": "CVA is…"}]}

    real = memory_router.conversation_store
    memory_router.conversation_store = _Convs
    _LLM.replies = [json.dumps({"lines": ["Asked about CVA; got the definition."]})]
    try:
        memory_router._journal_if_due(user)
        journal = memory_store.load_file(user["username"], "journal")
        assert "2026-07-21 · Basel chat — Asked about CVA; got the definition." in journal
        calls_before = len(_LLM.calls)
        memory_router._journal_if_due(user)  # same day -> no second LLM call
        assert len(_LLM.calls) == calls_before, "the pass must run once per day"
    finally:
        memory_router.conversation_store = real

    # Compaction validation: garbage keeps the journal, a real shrink is taken.
    long_text = "\n".join(f"2026-06-{d:02d} · chat — line." for d in range(1, 30))
    _LLM.replies = ["not json"]
    assert memory_judge.compact_journal(long_text, 200) is None
    _LLM.replies = [json.dumps({"text": "2026-06 · June digest."})]
    assert memory_judge.compact_journal(long_text, 200) == "2026-06 · June digest."
    print("  journal pass: dated lines from changed chats, daily stamp, compaction ✓")


def test_journal_provenance_cascade():
    user = "evo-prov"
    memory_store.clear(user)
    memory_store.append_journal(
        user,
        ["2026-07-20 · Chat A — first.", "2026-07-20 · Chat B — second.",
         "2026-07-21 · Chat A — third."],
        sources=["a", "b", "a"])
    edited = memory_store.load_file(user, "journal").replace("first.", "first (edited).")
    memory_store.save_file(user, "journal", edited)

    assert memory_store.forget_conversation(user, "a")
    text = memory_store.load_file(user, "journal")
    assert "third." not in text, "A's untouched line must cascade away"
    assert "first (edited)." in text, "an edited line is the user's — it survives"
    assert "second." in text, "B's line is untouched by A's deletion"
    assert not memory_store.forget_conversation(user, "a"), "already forgotten"

    memory_store.save_file(user, "journal", "2026-07 · July digest.")
    memory_store.prune_journal_index(user)
    assert not memory_store.forget_conversation(user, "b"), \
        "digested lines are past cascading — the index prunes itself"
    print("  provenance: cascade on delete, edits survive, digests prune ✓")


def test_journal_catchup_batching():
    from datetime import date as _date

    from app.routers import memory as memory_router

    user = {"username": "evo-catchup", "is_guest": False, "is_admin": False}
    memory_store.clear(user["username"])
    convs = [{"id": f"c{i}", "title": f"Chat {i}",
              "updated_at": f"2026-07-20T00:00:{i:02d}+00:00"} for i in range(10)]

    class _Convs:
        @staticmethod
        def list_summaries(username, is_guest):
            return convs[::-1]  # store returns recent-first

        @staticmethod
        def get(cid, username, is_guest):
            base = next(c for c in convs if c["id"] == cid)
            return {**base, "messages": [{"role": "user", "content": "q"},
                                         {"role": "assistant", "content": "a"}]}

    real = memory_router.conversation_store
    memory_router.conversation_store = _Convs
    _LLM.replies = [json.dumps({"lines": [f"sum {i}" for i in range(8)]}),
                    json.dumps({"lines": ["sum 8", "sum 9"]})]
    try:
        memory_router._journal_if_due(user)
        assert memory_store.journal_stamp(user["username"]) == \
            "2026-07-20T00:00:07+00:00", \
            "with leftovers the stamp stops at the last processed conversation"
        memory_router._journal_if_due(user)  # same day -> continues the catch-up
        journal = memory_store.load_file(user["username"], "journal")
        assert "Chat 0 — sum 0" in journal and "Chat 9 — sum 9" in journal, \
            "every changed conversation must eventually be journaled"
        assert memory_store.journal_stamp(user["username"])[:10] == \
            _date.today().isoformat(), "caught up -> the stamp closes the day"
    finally:
        memory_router.conversation_store = real
    print("  catch-up: >batch changes span passes, nothing silently dropped ✓")


def test_legacy_single_file_migrates_to_profile():
    user = "evo-legacy"
    legacy = memory_store._DIR / f"{user}.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    old_header = ("# User memory\n\nDurable facts about the user, saved via "
                  "/remember and the memory judge. Hand-editable — one fact per "
                  "`- ` line.\n\n")
    legacy.write_text(old_header + "- The user plays chess.\n", encoding="utf-8")
    text = memory_store.load_file(user, "profile")
    assert "The user plays chess." in text
    assert not legacy.exists(), "the legacy file becomes profile.md (moved, not copied)"
    assert "User memory" not in text, \
        "the old boilerplate header must be stripped on load"
    assert memory_store.context_block(user), "legacy content must still inject"
    print("  migration: legacy single file becomes profile.md, header stripped ✓")


def test_notes_dated_dedup_update_and_migration():
    user = "evo-notes"
    beliefs.delete_user_files(user)

    # Dated append + case-insensitive dedup.
    line = beliefs.append_belief("Output floors are too strict.", "dom", None,
                                 user, today=TODAY)
    assert line == f"Output floors are too strict. ({TODAY})"
    assert beliefs.append_belief("output floors are TOO strict.", "dom", None,
                                 user, today=TODAY) is None, "dedup must be case-blind"

    # A reversal REPLACES the old note in place; unknown targets defuse to adds.
    done = beliefs.apply_note_operations(
        [("Output floors are actually fine.", "Output floors are too strict."),
         ("CVA charges are underrated.", "A note that never existed.")],
        "dom", None, user, "2026-07-23")
    assert done == {"added": ["CVA charges are underrated."],
                    "updated": ["Output floors are actually fine."]}
    text = beliefs.read_beliefs("dom", None, user)
    assert "too strict" not in text and "actually fine. (2026-07-23)" in text

    # Legacy per-save file merges into the shared domain file on first read.
    legacy = beliefs._DIR / f"{user}__old-save.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("- Basel III is too complex.\n", encoding="utf-8")
    merged = beliefs.read_beliefs("dom", "old-save", user)
    assert "Basel III is too complex." in merged and not legacy.exists(), \
        "save-keyed notes must merge into the domain file and disappear"

    # Notes consolidation: garbage/growth rejected, a genuine merge accepted.
    lines = [f"Note {i}. (2026-06-01)" for i in range(10)]
    _LLM.replies = ["not json"]
    assert memory_judge.consolidate_notes(lines, 200) is None
    _LLM.replies = [json.dumps({"notes": ["Notes 0-9 merged. (2026-06-01)"]})]
    assert memory_judge.consolidate_notes(lines, 200) == \
        ["Notes 0-9 merged. (2026-06-01)"]
    print("  notes: dated dedup, reversal replaces, domain-merge, consolidation ✓")


def test_auto_route_wires_beliefs_to_context():
    from app.routers import memory as memory_router
    from app.schemas import ChatMessage, ChatRequest

    user = {"username": "evo-auto", "is_guest": False, "is_admin": False}
    memory_store.clear(user["username"])
    memory_store.mark_swept(user["username"], "9999-01-01")
    real_evolve = memory_judge.evolve
    memory_judge.evolve = lambda msgs, profile, now, today, notes=None: {
        "profile": [("Work", "The user is a quant.")],
        "archive": ["The user was a trader. (2026-07-22)"],
        "add": [("The user is studying for the CFA.", "2026-12-01")],
        "update": [], "delete": [], "retire": [],
        "beliefs": [("Vol targeting beats fixed weights.", None)]}
    try:
        req = ChatRequest(messages=[ChatMessage(role="user", content="…")],
                          domain="default", memory="my-save")
        res = memory_router.auto_memory(req, user=user)
    finally:
        memory_judge.evolve = real_evolve
    assert res["profile_updated"] == ["Work"]
    assert res["added"] == ["The user is studying for the CFA."]
    assert "The user is a quant." in res["context"] and "## Now" in res["context"]
    assert "The user was a trader." in memory_store.load_file(user["username"], "history")
    assert "Work" in res["memories"], "profile topics appear in the addressable list"
    assert res["beliefs_added"] == ["Vol targeting beats fixed weights."]
    note = beliefs.read_beliefs("default", "my-save", user["username"])
    assert "Vol targeting beats fixed weights." in note
    assert beliefs.read_beliefs("default", None, user["username"]) == note, \
        "notes follow the DOMAIN — a save and its live domain share one file"
    print("  /auto: sections woven, archive kept, opinions land in beliefs ✓")


TESTS = [
    test_operations_parse_and_validate,
    test_profile_sections,
    test_apply_now_operations,
    test_expiry_sweep,
    test_consolidation_never_loses_memory,
    test_remember_placement_and_fallback,
    test_journal_tail_and_recall,
    test_journal_daily_pass,
    test_journal_provenance_cascade,
    test_journal_catchup_batching,
    test_legacy_single_file_migrates_to_profile,
    test_notes_dated_dedup_update_and_migration,
    test_auto_route_wires_beliefs_to_context,
]

if __name__ == "__main__":
    failed = 0
    print(f"running topical-memory tests (state -> {_SCRATCH})…")
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
