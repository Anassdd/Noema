"""CUAD (Contract Understanding Atticus Dataset) -> noema-humanqa-v1.

CUAD (Hendrycks et al., NeurIPS 2021; The Atticus Project): 102 real commercial
contracts annotated BY LAWYERS across 41 clause categories ("Governing Law",
"Termination for Convenience", "Cap on Liability"...). Questions are kept
verbatim; the gold answer is the annotated clause text — and when the contract
simply has no such clause, the gold says so, which makes CUAD a refusal-
calibration test as well (the judge rubric scores "no such clause" as correct
only when that IS the gold).

Corpus documents = whole contracts. Each question is scoped to its contract
(scope_doc_id): the dataset's task is per-contract review, like FinanceBench's
per-filing questions. `type` = present | absent (does the clause exist), so the
report slices split extraction quality from refusal calibration.

Input: test.json from the CUAD data.zip (github.com/TheAtticusProject/cuad),
already SQuAD-format. --src points at it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.bench.adapters.util import write_json_atomic
from app.bench.store import RAW_DIR

GOLD_SOURCE = ("human (CUAD — Hendrycks et al. 2021, The Atticus Project; "
               "lawyer-annotated clauses across 41 categories, absences included)")
ABOUT = ("CUAD test split: real commercial contracts reviewed by lawyers across 41 "
         "clause categories. Gold = the annotated clause verbatim, or the absence of "
         "one — extraction quality and refusal calibration in one dataset.")

ABSENT_GOLD = "This contract contains no such clause."


def _doc_id(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()[:80]


def convert(src: Path, out: Path, max_contracts: int = 0) -> None:
    data = json.loads(src.read_text(encoding="utf-8"))["data"]
    if max_contracts:
        data = data[:max_contracts]
    documents, questions = [], []
    for contract in data:
        did = _doc_id(contract["title"])
        text = "\n\n".join(p["context"] for p in contract["paragraphs"])
        documents.append({"id": did, "title": contract["title"], "text": text})
        for para in contract["paragraphs"]:
            for qa in para["qas"]:
                spans = []
                for a in qa.get("answers", []):
                    t = (a.get("text") or "").strip()
                    if t and t not in spans:
                        spans.append(t)
                absent = qa.get("is_impossible") or not spans
                questions.append({
                    "question": qa["question"].strip(),
                    "answer": ABSENT_GOLD if absent else spans[0],
                    "alt_answers": [] if absent else spans[1:],
                    "evidence": "" if absent else spans[0],
                    "type": "absent" if absent else "present",
                    "doc_ids": [did], "scope_doc_id": did,
                })
    write_json_atomic({"format": "noema-humanqa-v1", "gold_source": GOLD_SOURCE,
                       "about": ABOUT, "documents": documents,
                       "questions": questions}, out)
    n_absent = sum(1 for q in questions if q["type"] == "absent")
    print(f"wrote {out} — {len(documents)} contracts, {len(questions)} questions "
          f"({len(questions) - n_absent} present / {n_absent} absent)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "cuad" / "test.json"))
    ap.add_argument("--out", default=str(RAW_DIR / "s2-cuad.json"))
    ap.add_argument("--max-contracts", type=int, default=0, help="0 = keep all")
    args = ap.parse_args()
    convert(Path(args.src), Path(args.out), args.max_contracts)


if __name__ == "__main__":
    main()
