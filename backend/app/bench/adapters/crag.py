"""CRAG (Meta, KDD Cup 2024) -> noema-humanqa-v1.

Input: the official crag_task_1_and_2_dev_v*.jsonl.bz2 release (github.com/
facebookresearch/CRAG, Git LFS). Each record is one question with its answer and
the 5 web pages a search engine returned for it (full HTML).

Slice taken, and why:
  - domains finance + open only (the slices relevant to Noema's target domain),
  - static questions only (answers don't drift, so a frozen corpus stays correct),
  - a question is kept only when >= MIN_PAGES of its 5 pages yield real text
    (dead/empty pages would make the gold unanswerable through no fault of the
    retriever).

Pages become the corpus documents (title + extracted text, capped per page),
deduplicated across questions. Questions carry doc_ids for cap selection but NO
scope_doc_id: CRAG is a corpus-wide search benchmark. CRAG's own question_type
taxonomy (simple, comparison, aggregation, multi-hop, false_premise...) is kept as
the gold `type`, so per-type report slices show where the graph pays off.
false_premise gold answers are CRAG's literal "invalid question".
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
from collections import Counter

from app.bench.adapters.util import cap_tokens, page_to_text, write_json_atomic
from app.bench.store import RAW_DIR

DOMAINS = {"finance", "open"}
MIN_PAGES = 4
PAGE_TOKEN_CAP = 6000
MIN_PAGE_CHARS = 200

GOLD_SOURCE = ("human (CRAG — Yang et al. 2024, Meta KDD Cup; "
               "finance+open static slice, answers as released)")
ABOUT = ("CRAG (Meta, KDD Cup 2024): human-written questions with verified answers, asked "
         "over the top-5 web pages a real search engine returned — retrieval over noisy web "
         "content, searched corpus-wide. This slice: finance + open domains, static questions "
         "only, pages deduplicated and text-extracted. Question types are CRAG's own "
         "(simple, comparison, aggregation, multi-hop, false-premise...) so per-type report "
         "slices show where the graph pays off; false-premise gold is 'invalid question'.")


def convert(src_path, max_questions: int = 0) -> dict:
    kept = []
    with bz2.open(src_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["domain"] not in DOMAINS or rec["static_or_dynamic"] != "static":
                continue
            pages = []
            for sr in rec.get("search_results", []):
                text = page_to_text(sr.get("page_result") or "")
                if len(text) < MIN_PAGE_CHARS:
                    continue
                title = (sr.get("page_name") or "").strip()
                text, tokens = cap_tokens(f"{title}\n\n{text}".strip(), PAGE_TOKEN_CAP)
                pages.append({"title": title, "text": text})
            if len(pages) >= MIN_PAGES:
                kept.append((rec, pages))

    kept.sort(key=lambda rp: hashlib.sha1(rp[0]["interaction_id"].encode()).hexdigest())
    if max_questions:
        kept = kept[:max_questions]

    documents, doc_index, questions = [], {}, []
    for rec, pages in kept:
        doc_ids = []
        for page in pages:
            h = hashlib.sha1(page["text"].encode("utf-8")).hexdigest()[:12]
            doc_id = f"web-{h}"
            if doc_id not in doc_index:
                doc_index[doc_id] = True
                documents.append({"id": doc_id, "title": page["title"], "text": page["text"]})
            if doc_id not in doc_ids:
                doc_ids.append(doc_id)
        questions.append({"question": rec["query"].strip(), "answer": str(rec["answer"]).strip(),
                          "alt_answers": [str(a).strip() for a in rec.get("alt_ans", []) if str(a).strip()],
                          "evidence": "", "type": rec["question_type"],
                          "doc_ids": doc_ids, "scope_doc_id": None})

    return {"format": "noema-humanqa-v1", "name": "crag-fin-open", "gold_source": GOLD_SOURCE,
            "about": ABOUT,
            "source_url": "https://github.com/facebookresearch/CRAG",
            "built_by": "app/bench/adapters/crag.py",
            "documents": documents, "questions": questions}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", help="path to crag_task_1_and_2_dev_v*.jsonl.bz2")
    ap.add_argument("--out", default=str(RAW_DIR / "crag-fin-open.json"))
    ap.add_argument("--max-questions", type=int, default=0, help="0 = keep all")
    args = ap.parse_args()

    data = convert(args.src, args.max_questions)
    write_json_atomic(data, args.out)
    types = Counter(q["type"] for q in data["questions"])
    print(f"{args.out}: {len(data['questions'])} questions, {len(data['documents'])} pages")
    print("types:", dict(types))


if __name__ == "__main__":
    main()
