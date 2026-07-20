"""Automatic memory-evolution tests — no network, no LLM:

    backend/.venv/bin/python tests/test_memory_evolution.py

The judge's LLM call is stubbed with canned JSON; state goes to a scratch dir.
Covers: operation parsing (with the safety downgrades — a hallucinated update
target becomes an add, a hallucinated delete is dropped), in-place application,
consolidation validation (a bad reply can never lose the memory), and the /auto
route wiring beliefs into the current memory context.
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

KNOWN = ["The user's name is Anas.", "The user lives in Lyon."]


def test_operations_parse_and_validate():
    _LLM.replies = [json.dumps({
        "operations": [
            {"op": "update", "replaces": "The user lives in Lyon.",
             "fact": "The user lives in Paris."},
            {"op": "add", "fact": "The user works at a bank."},
            {"op": "update", "replaces": "The user drives a Ferrari.",  # hallucinated target
             "fact": "The user cycles to work."},
            {"op": "delete", "fact": "The user owns a boat."},          # hallucinated target
            {"op": "delete", "fact": "the user's name is anas."},       # case-tolerant match
        ],
        "beliefs": ["Basel III output floors are too strict."],
    })]
    ops = memory_judge.evolve([{"role": "user", "content": "hi"}], KNOWN)
    assert ops["update"] == [("The user lives in Lyon.", "The user lives in Paris.")]
    assert ops["add"] == ["The user works at a bank.", "The user cycles to work."], \
        "an update with an unknown target must downgrade to add, never vanish"
    assert ops["delete"] == ["The user's name is Anas."], \
        "delete must match case-insensitively and drop unknown targets"
    assert ops["beliefs"] == ["Basel III output floors are too strict."]
    print("  operation parsing: valid ops kept, hallucinated targets defused ✓")


def test_apply_operations_in_place():
    user = "evo-user"
    memory_store.replace_all(user, list(KNOWN))
    memories = memory_store.apply_operations(
        user,
        add=["The user works at a bank.", "The user's name is Anas."],  # dup ignored
        update=[("The user lives in Lyon.", "The user lives in Paris.")],
        delete=[])
    assert memories == ["The user's name is Anas.", "The user lives in Paris.",
                        "The user works at a bank."], "update must keep the fact's position"
    memories = memory_store.apply_operations(user, add=[], update=[],
                                             delete=["The user's name is Anas."])
    assert memories == ["The user lives in Paris.", "The user works at a bank."]
    print("  apply: in-place update, dedup on add, delete removes ✓")


def test_consolidation_never_loses_memory():
    memories = [f"The user fact {i}." for i in range(10)]
    _LLM.replies = [json.dumps({"facts": ["The user facts 0-9 merged."]})]
    assert memory_judge.consolidate(memories) == ["The user facts 0-9 merged."]
    _LLM.replies = ["not json at all"]
    assert memory_judge.consolidate(memories) is None, "garbage reply -> keep original"
    _LLM.replies = [json.dumps({"facts": memories + ["invented extra fact"]})]
    assert memory_judge.consolidate(memories) is None, "a GROWING 'compaction' is suspect"
    _LLM.replies = [json.dumps({"facts": []})]
    assert memory_judge.consolidate(memories) is None, "an empty reply must never wipe"
    print("  consolidation: only a genuine compaction is accepted ✓")


def test_auto_route_wires_beliefs_to_context():
    from app.routers import memory as memory_router
    from app.schemas import ChatMessage, ChatRequest

    user = {"username": "evo-user2", "is_guest": False, "is_admin": False}
    memory_store.replace_all(user["username"], [])
    real_evolve = memory_judge.evolve
    memory_judge.evolve = lambda msgs, known: {
        "add": ["The user is a quant."], "update": [], "delete": [],
        "beliefs": ["Vol targeting beats fixed weights."]}
    try:
        req = ChatRequest(messages=[ChatMessage(role="user", content="…")],
                          domain="default", memory="my-save")
        res = memory_router.auto_memory(req, user=user)
    finally:
        memory_judge.evolve = real_evolve
    assert res["added"] == ["The user is a quant."]
    assert res["memories"] == ["The user is a quant."]
    note = beliefs.read_beliefs("default", "my-save", user["username"])
    assert "Vol targeting beats fixed weights." in note, \
        "asserted opinions must land in the SELECTED memory context's beliefs"
    print("  /auto: facts evolve the list, opinions land in the context's beliefs ✓")


def test_markdown_prose_survives_operations():
    user = "evo-md-user"
    memory_store.save_markdown(
        "# My memory\n\nNotes I keep by hand.\n\n"
        "## Facts\n- The user lives in Lyon.\n- The user plays chess.\n\n"
        "A closing remark.\n", user)
    assert memory_store.load_memories(user) == [
        "The user lives in Lyon.", "The user plays chess."]

    memory_store.apply_operations(
        user, add=["The user works at a bank."],
        update=[("The user lives in Lyon.", "The user lives in Paris.")],
        delete=["The user plays chess."])
    md = memory_store.load_markdown(user)
    assert "Notes I keep by hand." in md and "## Facts" in md and "A closing remark." in md, \
        "automatic operations must never touch the user's own prose"
    assert "- The user lives in Paris." in md and "Lyon" not in md
    assert "chess" not in md and "- The user works at a bank." in md

    # Consolidation swaps the bullets but keeps the prose too.
    memory_store.replace_all(user, ["The user is a Paris-based banker."])
    md = memory_store.load_markdown(user)
    assert "Notes I keep by hand." in md and "A closing remark." in md
    assert memory_store.load_memories(user) == ["The user is a Paris-based banker."]
    print("  markdown editing: prose/headings survive every automatic operation ✓")


TESTS = [
    test_operations_parse_and_validate,
    test_apply_operations_in_place,
    test_consolidation_never_loses_memory,
    test_auto_route_wires_beliefs_to_context,
    test_markdown_prose_survives_operations,
]

if __name__ == "__main__":
    failed = 0
    print(f"running memory-evolution tests (state -> {_SCRATCH})…")
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
