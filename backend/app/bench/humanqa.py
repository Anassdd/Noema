"""Human-gold loader — the generic path for benchmarks that arrive WITH their own
QA pairs (CRAG, FinanceBench, Basel-FAQ...), converted by an adapter
(app/bench/adapters/) into one raw file:

    backend/data/bench/<name>.json
    {"format": "noema-humanqa-v1", "gold_source": "human (...)",
     "documents": [{"id", "title", "text"}],
     "questions": [{"question", "answer", "alt_answers", "evidence", "type",
                    "doc_ids": [...], "scope_doc_id": "<doc id>" | null}]}

Like the QASPER path: documents are ingested WHOLE and the gold is pre-approved
human data (the Draft/Verify machinery is not needed). Unlike QASPER, selection
walks QUESTIONS in stable hash order and pulls in each question's documents until
the cap is hit — a question only enters the gold when EVERY document it needs made
it into the corpus, so the gold never asks about evidence the cap cut away.

`scope_doc_id` set -> the question runs with per-document retrieval scoping under
the runner's scope="auto" (FinanceBench: one filing per question). null -> the
question searches the whole corpus (CRAG: a shared web-page corpus).

Re-preparing REGENERATES gold.json (manual edits to human gold are lost).
"""

from __future__ import annotations

import hashlib
import json

from app.bench import store
from app.chunking.tokens import count_tokens

FORMAT = "noema-humanqa-v1"


def is_humanqa(path) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            return FORMAT in fh.read(4096)
    except OSError:
        return False


def prepare(dataset: str, cap_tokens: int) -> dict:
    raw = store.RAW_DIR / f"{dataset}.json"
    data = json.loads(raw.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"Not a {FORMAT} file.")
    docs_by_id = {d["id"]: d for d in data["documents"]}

    ordered = sorted(data["questions"],
                     key=lambda q: hashlib.sha1(f"{q['question']}|{q.get('answer', '')}".encode()).hexdigest())
    doc_tokens: dict[str, int] = {}

    def tokens(doc_id: str) -> int:
        if doc_id not in doc_tokens:
            doc_tokens[doc_id] = count_tokens(docs_by_id[doc_id]["text"])
        return doc_tokens[doc_id]

    selected: list[str] = []
    selected_set: set[str] = set()
    gold, total = [], 0
    for q in ordered:
        ids = q.get("doc_ids") or []
        if not ids or any(i not in docs_by_id for i in ids):
            continue
        need = [i for i in ids if i not in selected_set]
        cost = sum(tokens(i) for i in need)
        if need and total + cost > cap_tokens:
            continue  # question's documents don't fit — try smaller later ones
        for i in need:
            selected.append(i)
            selected_set.add(i)
        total += cost
        n = len(gold) + 1
        gold.append({"id": f"q{n:03d}", "n": n,
                     "doc_id": q.get("scope_doc_id") or "", "source": "human",
                     "question": q["question"].strip(), "answer": str(q["answer"]).strip(),
                     "alt_answers": [a for a in q.get("alt_answers", []) if a],
                     "evidence": q.get("evidence", ""),
                     "type": q.get("type") or "factoid", "status": "approved"})

    if not gold:
        raise ValueError("No question's documents fit — raise the cap (documents are ingested whole).")

    docs, corpus_hash = [], hashlib.sha256()
    for doc_id in selected:
        d = docs_by_id[doc_id]
        docs.append({"id": doc_id, "text": d["text"], "tokens": tokens(doc_id),
                     "truncated": False, "title": d.get("title", "")})
        corpus_hash.update(doc_id.encode())
        corpus_hash.update(d["text"].encode("utf-8"))

    store.save_corpus(dataset, docs)
    store.save_gold(dataset, gold)
    manifest = store.load_manifest(dataset)
    manifest["prepared"] = {
        "cap_tokens": cap_tokens,
        "docs": len(docs),
        "tokens": total,
        "corpus_hash": corpus_hash.hexdigest()[:16],
        "unique_contexts_in_file": len(docs_by_id),
        "questions_in_file": len(data["questions"]),
        "questions_kept": len(gold),
        "gold_source": data.get("gold_source", "human"),
    }
    store.save_manifest(dataset, manifest)
    return manifest["prepared"]
