"""French-parity locks — no network, no LLM:

    backend/.venv/bin/python tests/test_french.py

The company is French and half the corpus is French; these tests pin the places
where English-only behavior used to hide: BM25 accent folding, language-matched
contextual blurbs, source-language graph/LightRAG extraction, memory facts in the
user's language — and the fingerprint bumps that keep old builds from silently
mixing with language-fixed ones.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("OPENAI_API_KEY", "test-key-never-called")
BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.retrieval.bm25 import BM25  # noqa: E402


def test_bm25_is_accent_insensitive():
    idx = BM25().build([
        ("fr", "La réglementation bancaire européenne s'applique aux établissements."),
        ("en", "Unrelated text about weather patterns and cloud formation."),
    ])
    for query in ("reglementation europeenne",          # unaccented typing
                  "réglementation européenne",          # accented typing
                  "REGLEMENTATION"):                    # caps, no accents
        hits = idx.search(query, k=1)
        assert hits and hits[0][0] == "fr", f"{query!r} must hit the French chunk, got {hits}"
    print("  bm25: accented and unaccented spellings meet in the same index ✓")


def test_prompts_speak_the_source_language():
    from app import memory_judge
    from app.graph import store as graph_store
    from app.retrieval import contextual

    for tpl in (contextual.PROMPT_TEMPLATE, contextual.EXCERPT_TEMPLATE):
        assert "same language as the document" in tpl, "blurbs must follow the doc's language"
    for ins in (graph_store.DEFAULT_EXTRACTION_INSTRUCTIONS,
                graph_store.DOCUMENT_EXTRACTION_INSTRUCTIONS):
        assert "language of the source text" in ins, "graph facts must not be translated"
    assert "LANGUAGE THE USER SPEAKS" in memory_judge._SYSTEM, \
        "memory facts must be written in the user's language"

    lightrag_src = (BACKEND / "app" / "lightrag" / "store.py").read_text()
    assert "addon_params" in lightrag_src and "same language as the source text" in lightrag_src, \
        "LightRAG must extract in the source language (addon_params)"
    print("  prompts: contextualizer, both extractors and the memory judge follow the source language ✓")


def test_build_fingerprints_bumped_for_language_parity():
    from app.bench import runner

    assert runner._EP_VERSION == "ep700-v3", \
        "language-parity prompt changes alter builds — the fingerprint must move"
    assert runner._LR_VERSION == "lr700-v2", \
        "the LightRAG language param alters its leg — its fingerprint must move"
    print("  fingerprints: ep700-v3 / lr700-v2 — no silent build_skip across the change ✓")


TESTS = [
    test_bm25_is_accent_insensitive,
    test_prompts_speak_the_source_language,
    test_build_fingerprints_bumped_for_language_parity,
]

if __name__ == "__main__":
    failed = 0
    print("running French-parity tests…")
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
