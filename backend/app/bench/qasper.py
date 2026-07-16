"""QASPER loader — human-gold benchmark over research papers.

QASPER (Dasigi et al., NAACL 2021): NLP papers with questions written by humans who
read only title+abstract, answered by OTHER humans reading the full paper, evidence
paragraphs marked. Drop the release file (qasper-train-v0.3.json or dev) into
backend/data/bench/ as `<name>.json`.

Differences from the jsonl path: papers are ingested WHOLE (4-6k tokens each — the
cap selects how many papers, it never cuts one), and the gold arrives from the
dataset itself, pre-approved with `source: human` — the Draft/Verify machinery is
not needed and the page hides it.

Re-preparing REGENERATES gold.json from the selected papers (manual edits to
human gold are not expected; deletions would be lost).
"""

from __future__ import annotations

import hashlib
import json

from app.bench import store
from app.bench.goldgen import NULL_ANSWER
from app.chunking.tokens import count_tokens

GOLD_SOURCE = "human (QASPER annotators — Dasigi et al. 2021)"
ABOUT = ("QASPER (Dasigi et al., NAACL 2021): questions written by NLP researchers who read "
         "only a paper's title and abstract, answered by other researchers reading the full "
         "paper, with evidence paragraphs marked. Papers are ingested whole; the human gold "
         "arrives pre-approved when you prepare.")


def is_qasper(path) -> bool:
    """Cheap sniff: `full_text` shows up within a paper's opening keys. (`qas` comes
    AFTER each ~30k-char paper body, so requiring it in the head would false-negative
    on the real release — prepare() does the strict structural validation instead.)"""
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(100_000)
        return '"full_text"' in head
    except OSError:
        return False


def _paper_text(paper: dict) -> str:
    parts = [paper.get("title", ""), paper.get("abstract", "")]
    for section in paper.get("full_text", []):
        name = (section.get("section_name") or "").strip()
        paras = [p for p in section.get("paragraphs", []) if p and p.strip()]
        if not paras:
            continue
        if name:
            parts.append(f"## {name}")
        parts.extend(paras)
    return "\n\n".join(p for p in parts if p and p.strip())


def _map_answer(ans: dict) -> tuple[str, str, str]:
    """QASPER's answer annotation -> (gold answer, type, evidence quote)."""
    evidence = next((e for e in ans.get("evidence", [])
                     if e and not e.startswith("FLOAT SELECTED")), "")
    if ans.get("unanswerable"):
        return NULL_ANSWER, "null", ""
    if ans.get("yes_no") is not None:
        return ("Yes" if ans["yes_no"] else "No"), "factoid", evidence
    if ans.get("extractive_spans"):
        return "; ".join(ans["extractive_spans"]), "factoid", evidence
    return (ans.get("free_form_answer") or "").strip(), "synthesis", evidence


def prepare(dataset: str, cap_tokens: int) -> dict:
    """Select whole papers (stable hash order) up to the cap; corpus + human gold."""
    raw = store.RAW_DIR / f"{dataset}.json"
    papers = json.loads(raw.read_text(encoding="utf-8"))
    if not (isinstance(papers, dict) and papers
            and all(isinstance(p, dict) and "full_text" in p and "qas" in p
                    for p in list(papers.values())[:3])):
        raise ValueError("Not QASPER structure (expected {paper_id: {title, abstract, "
                         "full_text, qas}}).")
    ordered = sorted(papers.items(), key=lambda kv: hashlib.sha1(kv[0].encode()).hexdigest())

    docs, gold, corpus_hash, total = [], [], hashlib.sha256(), 0
    for paper_id, paper in ordered:
        text = _paper_text(paper)
        tokens = count_tokens(text)
        if docs and total + tokens > cap_tokens:
            continue  # paper doesn't fit — try smaller later ones (whole papers only)
        doc_id = f"{dataset}-{hashlib.sha1(paper_id.encode()).hexdigest()[:8]}"
        docs.append({"id": doc_id, "text": text, "tokens": tokens, "truncated": False,
                     "paper_id": paper_id, "title": paper.get("title", "")})
        total += tokens
        corpus_hash.update(doc_id.encode())
        corpus_hash.update(text.encode("utf-8"))

        for qa in paper.get("qas", []):
            annotations = qa.get("answers", [])
            if not qa.get("question") or not annotations:
                continue
            answer, qtype, evidence = _map_answer(annotations[0].get("answer", {}))
            if not answer:
                continue
            # QASPER questions carry SEVERAL annotators' answers — all are gold.
            # Judging against only one marks agreeing candidates wrong.
            alts = []
            if qtype != "null":
                for ann in annotations[1:]:
                    alt, alt_type, _ = _map_answer(ann.get("answer", {}))
                    if alt and alt_type != "null" and alt != answer and alt not in alts:
                        alts.append(alt)
            n = len(gold) + 1
            gold.append({"id": f"q{n:03d}", "n": n, "doc_id": doc_id, "source": "human",
                         "question": qa["question"].strip(), "answer": answer,
                         "alt_answers": alts, "evidence": evidence, "type": qtype,
                         "status": "approved"})
        if total >= cap_tokens:
            break

    if not docs:
        raise ValueError("No papers fit — raise the cap (papers are ingested whole).")

    store.save_corpus(dataset, docs)
    store.save_gold(dataset, gold)
    manifest = store.load_manifest(dataset)
    manifest["prepared"] = {
        "cap_tokens": cap_tokens,
        "docs": len(docs),
        "tokens": total,
        "corpus_hash": corpus_hash.hexdigest()[:16],
        "unique_contexts_in_file": len(ordered),
        "gold_source": GOLD_SOURCE,
    }
    store.save_manifest(dataset, manifest)
    return manifest["prepared"]
