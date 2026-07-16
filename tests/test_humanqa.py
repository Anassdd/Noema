"""Human-gold loader tests — no network, temp dirs only:

    backend/.venv/bin/python tests/test_humanqa.py

Covers the noema-humanqa-v1 contract: question-driven whole-document selection
(a question enters the gold only when EVERY document it needs fits the cap),
scope passthrough, deterministic output, and format sniffing.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

TMP = Path(tempfile.mkdtemp(prefix="humanqa-test-"))
os.environ["BENCH_DATA_DIR"] = str(TMP / "raw")
os.environ["BENCH_WORK_DIR"] = str(TMP / "work")

from app.bench import datasets, humanqa, store  # noqa: E402
from app.chunking.tokens import count_tokens  # noqa: E402

WORDS_50 = " ".join(f"w{i}" for i in range(50))
DOC_TOKENS = count_tokens(WORDS_50)

RAW = {
    "format": "noema-humanqa-v1",
    "gold_source": "human (test fixture)",
    "documents": [
        {"id": "d1", "title": "Doc one", "text": WORDS_50},
        {"id": "d2", "title": "Doc two", "text": WORDS_50},
        {"id": "big", "title": "Huge doc", "text": " ".join(f"tok{i}" for i in range(5000))},
    ],
    "questions": [
        {"question": "Only needs d1?", "answer": "yes", "doc_ids": ["d1"], "scope_doc_id": "d1",
         "evidence": "w1 w2", "type": "binary"},
        {"question": "Needs d1 and d2?", "answer": "both", "doc_ids": ["d1", "d2"], "scope_doc_id": None},
        {"question": "Needs the huge doc?", "answer": "no fit", "doc_ids": ["big"], "scope_doc_id": "big"},
        {"question": "Dangling doc ref?", "answer": "dropped", "doc_ids": ["ghost"], "scope_doc_id": None},
    ],
}


def write_raw(name="fixture"):
    store.RAW_DIR.mkdir(parents=True, exist_ok=True)
    (store.RAW_DIR / f"{name}.json").write_text(json.dumps(RAW), encoding="utf-8")


def test_sniff_and_routing():
    write_raw()
    assert humanqa.is_humanqa(store.RAW_DIR / "fixture.json")
    prepared = datasets.prepare("fixture", cap_tokens=500)
    assert prepared["gold_source"] == "human (test fixture)"
    print("sniff + routing ok")


def test_question_driven_selection():
    write_raw()
    prepared = humanqa.prepare("fixture", cap_tokens=500)
    gold = store.load_gold("fixture")
    corpus = store.load_corpus("fixture")
    asked = {q["question"] for q in gold}
    assert "Needs the huge doc?" not in asked, "a question whose doc exceeds the cap must drop"
    assert "Dangling doc ref?" not in asked, "a question referencing a missing doc must drop"
    assert {"Only needs d1?", "Needs d1 and d2?"} == asked
    assert {d["id"] for d in corpus} == {"d1", "d2"}, "corpus = exactly the docs the gold needs"
    assert all(q["status"] == "approved" and q["source"] == "human" for q in gold)
    scope = {q["question"]: q["doc_id"] for q in gold}
    assert scope["Only needs d1?"] == "d1" and scope["Needs d1 and d2?"] == ""
    assert prepared["docs"] == 2 and prepared["questions_in_file"] == 4
    print("question-driven selection ok")


def test_all_docs_must_fit():
    write_raw()
    humanqa.prepare("fixture", cap_tokens=DOC_TOKENS + 5)
    gold = store.load_gold("fixture")
    assert {q["question"] for q in gold} == {"Only needs d1?"}, \
        "the two-doc question must drop when only one doc fits"
    print("all-docs-must-fit ok")


def test_deterministic():
    write_raw()
    h1 = humanqa.prepare("fixture", cap_tokens=500)["corpus_hash"]
    h2 = humanqa.prepare("fixture", cap_tokens=500)["corpus_hash"]
    assert h1 == h2
    print("deterministic ok")


def test_cap_too_small():
    write_raw()
    try:
        humanqa.prepare("fixture", cap_tokens=3)
    except ValueError:
        print("cap-too-small raises ok")
    else:
        raise AssertionError("expected ValueError when nothing fits")


if __name__ == "__main__":
    test_sniff_and_routing()
    test_question_driven_selection()
    test_all_docs_must_fit()
    test_deterministic()
    test_cap_too_small()
    print("all humanqa tests passed")
