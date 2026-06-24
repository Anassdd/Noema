"""Contextualizer tests — runnable with plain python, no LLM calls (mocked):

    backend/.venv/bin/python tests/test_contextual.py

Verifies the prompt structure and how the context blurb is assembled onto the chunk,
without spending money or needing the network.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import llm_client  # noqa: E402
from app.chunking import chunk_markdown  # noqa: E402
from app.retrieval import contextual  # noqa: E402

DOC = "# Intro\n\nThis paper studies Hölder inequalities.\n\n## Methods\n\nWe use convexity."


class _Usage:
    prompt_tokens, completion_tokens, total_tokens, cached_tokens = 120, 12, 132, 64


class _Result:
    usage = _Usage()
    model = "fake-model"

    def __init__(self, text):
        self.text = text


def _patch(fake):
    """Swap llm_client.chat with `fake`, return a restore()."""
    original = llm_client.chat
    llm_client.chat = fake
    return lambda: setattr(llm_client, "chat", original)


def test_prompt_contains_document_and_chunk():
    captured = {}

    def fake(messages, **kw):
        captured["content"] = messages[0]["content"]
        captured["kw"] = kw
        return _Result("From the Methods section.")

    restore = _patch(fake)
    try:
        chunks = chunk_markdown(DOC, doc_id="d")
        contextual.contextualize_chunk(DOC, chunks[-1])
    finally:
        restore()
    c = captured["content"]
    assert "<document>" in c and "</document>" in c, "document not wrapped"
    assert "<chunk>" in c and "</chunk>" in c, "chunk not wrapped"
    assert "Hölder" in c, "document body missing from prompt"
    assert c.index("<document>") < c.index("<chunk>"), "document must come first (cacheable prefix)"
    assert captured["kw"].get("temperature") == 0.0, "should request temperature 0"
    print("  prompt_structure: document-first, chunk wrapped, temp=0 ✓")


def test_assembles_context_onto_chunk():
    restore = _patch(lambda messages, **kw: _Result("  This chunk is from the intro.  "))
    try:
        chunks = chunk_markdown(DOC, doc_id="d")
        out = contextual.contextualize_chunks(DOC, chunks)
    finally:
        restore()
    assert len(out) == len(chunks)
    cc = out[0]
    assert cc.context == "This chunk is from the intro.", "context not stripped/captured"
    assert cc.text.startswith("This chunk is from the intro."), "context not prepended"
    assert cc.chunk.text in cc.text, "original chunk text must be preserved in the payload"
    assert cc.prompt_tokens == 120 and cc.completion_tokens == 12, "token accounting wrong"
    assert cc.total_tokens == 132
    print(f"  assembly: {len(out)} contextual chunks, context prepended, tokens summed ✓")


def test_empty_context_is_safe():
    restore = _patch(lambda messages, **kw: _Result(""))
    try:
        out = contextual.contextualize_chunks(DOC, chunk_markdown(DOC, doc_id="d"))
    finally:
        restore()
    # with no context, text falls back to the bare chunk (no leading blank lines)
    assert out[0].text == out[0].chunk.text, "empty context should leave the chunk unchanged"
    print("  empty_context: falls back to bare chunk ✓")


def test_no_chunks():
    restore = _patch(lambda *a, **k: _Result("x"))
    try:
        assert contextual.contextualize_chunks(DOC, []) == []
    finally:
        restore()
    print("  no_chunks: returns [] ✓")


def test_cached_tokens_passthrough():
    restore = _patch(lambda messages, **kw: _Result("Intro context."))
    try:
        out = contextual.contextualize_chunks(DOC, chunk_markdown(DOC, doc_id="d"))
    finally:
        restore()
    assert out[0].cached_tokens == 64, "cached_tokens not carried from usage"
    print("  cached_tokens: passed through from usage ✓")


# ---- where it can go wrong: the LLM ignores 'context only' and adds noise ----
def test_clean_strips_preamble():
    for raw, want in [
        ("Here is the succinct context: This is the intro.", "This is the intro."),
        ("Here is a short context for the chunk: From methods.", "From methods."),
        ("Context: Belongs to results.", "Belongs to results."),
        ("The context is: Section two.", "Section two."),
    ]:
        got = contextual._clean_context(raw)
        assert got == want, f"preamble not stripped: {raw!r} -> {got!r}"
    print("  clean_preamble: 4 lead-ins stripped ✓")


def test_clean_strips_quotes_and_fences():
    assert contextual._clean_context('"From the intro."') == "From the intro."
    assert contextual._clean_context("'From the intro.'") == "From the intro."
    assert contextual._clean_context("```\nFrom the intro.\n```") == "From the intro."
    print("  clean_quotes_fences: quotes and code fences stripped ✓")


def test_clean_preserves_real_context_and_french():
    clean = "This chunk introduces Hölder inequalities in the opening section."
    assert contextual._clean_context(clean) == clean, "clean context must be untouched"
    fr = "Le chunk se situe dans la section sur l'inégalité de Hölder."
    assert contextual._clean_context(fr) == fr, "French context must be preserved verbatim"
    print("  clean_preserve: clean + French context untouched ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running contextualizer tests…")
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
