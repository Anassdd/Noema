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


# ---- excerpt mode: documents too big to ride whole -------------------------

def _big_doc(sections=("Alpha", "Beta", "Gamma", "Delta"), paras=8):
    parts = []
    for s in sections:
        parts.append(f"# {s} section")
        parts.extend(f"In {s}, paragraph {i} explains the {s.lower()} topic number {i} "
                     "in enough words to carry a few dozen tokens of body text."
                     for i in range(paras))
    return "\n\n".join(parts)


def _small_excerpt_knobs():
    """Shrink the excerpt anatomy so a page-sized fixture exercises batching."""
    saved = (contextual._HEAD_TOKENS, contextual._MARGIN_TOKENS, contextual._MIN_SPAN_TOKENS)
    contextual._HEAD_TOKENS, contextual._MARGIN_TOKENS, contextual._MIN_SPAN_TOKENS = 60, 40, 50

    def restore():
        (contextual._HEAD_TOKENS, contextual._MARGIN_TOKENS,
         contextual._MIN_SPAN_TOKENS) = saved
    return restore


def _run_excerpted(doc, chunks, part_tokens=340):
    """contextualize with a tiny cap (forcing excerpt mode), capturing every prompt."""
    prompts = []

    def fake(messages, **kw):
        prompts.append(messages[0]["content"])
        return _Result("A situating blurb.")

    restore_llm, restore_knobs = _patch(fake), _small_excerpt_knobs()
    try:
        out = contextual.contextualize_chunks(doc, chunks, doc_cap=50, part_tokens=part_tokens)
    finally:
        restore_llm()
        restore_knobs()
    return out, prompts


def _prefix(prompt):
    return prompt.split("Here is the chunk", 1)[0]


def test_cap_switches_modes():
    doc = _big_doc()
    chunks = chunk_markdown(doc, doc_id="d", target_tokens=60)
    from app.chunking.tokens import count_tokens
    prompts = []

    def fake(messages, **kw):
        prompts.append(messages[0]["content"])
        return _Result("Blurb.")

    restore = _patch(fake)
    try:
        whole = contextual.contextualize_chunks(doc, chunks, doc_cap=count_tokens(doc))
    finally:
        restore()
    assert all("<document>" in p and "<document_excerpt>" not in p for p in prompts)
    assert not any(c.excerpted for c in whole), "under the cap must stay whole-doc mode"

    out, prompts = _run_excerpted(doc, chunks)
    assert all("<document_excerpt>" in p for p in prompts)
    assert all(c.excerpted for c in out), "over the cap must mark chunks excerpted"
    print("  cap_switch: ≤cap whole-doc (unchanged), >cap excerpt mode ✓")


def test_excerpt_batches_share_prefix_and_cover_chunks():
    doc = _big_doc()
    chunks = chunk_markdown(doc, doc_id="d", target_tokens=60)
    out, prompts = _run_excerpted(doc, chunks)
    assert len(out) == len(chunks) and all(cc.chunk is c for cc, c in zip(out, chunks))
    prefixes = [_prefix(p) for p in prompts]
    distinct = list(dict.fromkeys(prefixes))
    assert 1 < len(distinct) < len(chunks), f"expected several shared batches, got {len(distinct)}"
    for i, p in enumerate(prompts):  # a chunk must sit inside its own excerpt
        assert chunks[i].text in _prefix(p), f"chunk {i} missing from its excerpt"
    assert prefixes == sorted(prefixes, key=distinct.index), "batches must be consecutive"
    print(f"  excerpt_batches: {len(distinct)} shared prefixes over {len(chunks)} chunks, "
          "every chunk inside its own excerpt ✓")


def test_excerpt_head_and_sections():
    doc = _big_doc()
    chunks = chunk_markdown(doc, doc_id="d", target_tokens=60)
    out, prompts = _run_excerpted(doc, chunks)
    head = chunks[0].text
    assert all(head in _prefix(p) for p in prompts), "document head must open every excerpt"
    by_prefix = {}
    for i, p in enumerate(prompts):
        by_prefix.setdefault(_prefix(p), []).append(chunks[i].header_path[0])
    mixed = [set(secs) for secs in by_prefix.values() if len(set(secs)) > 1]
    assert not mixed, f"batches must not straddle sections: {mixed}"
    print(f"  excerpt_head_sections: head in all {len(prompts)} excerpts, "
          f"{len(by_prefix)} batches all section-pure ✓")


# ---- concurrency: prime the cache first, then parallel workers -------------

def test_concurrent_prime_first_and_order():
    import threading
    doc = _big_doc()
    chunks = chunk_markdown(doc, doc_id="d", target_tokens=60)
    events, lock = [], threading.Lock()

    def fake(messages, **kw):
        chunk_body = messages[0]["content"].split("<chunk>\n", 1)[1].split("\n</chunk>", 1)[0]
        with lock:
            events.append(("start", chunk_body))
        with lock:
            events.append(("end", chunk_body))
        return _Result(f"blurb")

    restore = _patch(fake)
    try:
        from app.chunking.tokens import count_tokens
        out = contextual.contextualize_chunks(doc, chunks, doc_cap=count_tokens(doc),
                                              concurrency=4)
    finally:
        restore()
    assert [cc.chunk for cc in out] == chunks, "results must keep chunk order"
    assert events[0] == ("start", chunks[0].text) and events[1] == ("end", chunks[0].text), \
        "the first (cache-priming) call must run alone before any worker starts"
    assert len(events) == 2 * len(chunks)
    print(f"  concurrency: prime-first honored, order kept over {len(chunks)} chunks ✓")


def test_concurrency_one_is_sequential():
    doc = _big_doc()
    chunks = chunk_markdown(doc, doc_id="d", target_tokens=60)
    order = []
    restore = _patch(lambda messages, **kw: (order.append(1), _Result("b"))[1])
    try:
        out = contextual.contextualize_chunks(doc, chunks, doc_cap=10**9, concurrency=1)
    finally:
        restore()
    assert len(out) == len(chunks) == len(order)
    print("  concurrency=1: fully sequential fallback works ✓")


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
