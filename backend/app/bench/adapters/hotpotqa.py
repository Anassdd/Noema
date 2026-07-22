"""HotpotQA (dev, distractor setting) -> noema-humanqa-v1.

HotpotQA (Yang et al., EMNLP 2018) is THE knowledge-graph stress test: every
question requires linking facts across TWO Wikipedia articles (bridge or
comparison), with the supporting sentences human-annotated. The distractor
setting ships each question with its 2 gold paragraphs plus 8 lexically-similar
distractors — exactly the trap dense retrieval falls into and a graph should not.

Corpus documents = unique Wikipedia paragraphs (deduped by title across
questions). Questions carry all 10 context titles as doc_ids — the cap keeps a
question only when its gold AND its distractors made it in, preserving the
benchmark's difficulty — and NO scope_doc_id: multi-hop search is corpus-wide by
construction. `evidence` = the annotated supporting sentences; `type` keeps
HotpotQA's bridge/comparison split so report slices show where the graph pays off.

Input: the official dev_distractor JSON (public, ~45 MB), via --download or --src.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from app.bench.adapters.util import write_json_atomic
from app.bench.store import RAW_DIR

URL = "http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json"

GOLD_SOURCE = ("human (HotpotQA dev distractor — Yang et al. 2018; crowdsourced "
               "multi-hop questions with annotated supporting sentences)")
ABOUT = ("HotpotQA dev (distractor setting): every question needs facts from two "
         "Wikipedia articles, shipped alongside eight similar-looking distractor "
         "paragraphs. The knowledge-graph stress test — bridge/comparison slices "
         "show whether graph traversal beats dense similarity.")


def _doc_id(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()


def convert(src: Path, out: Path, max_questions: int = 0) -> None:
    items = json.loads(src.read_text(encoding="utf-8"))
    if max_questions:
        items = items[:max_questions]
    docs: dict[str, dict] = {}
    questions = []
    for it in items:
        sent_by_title = {}
        doc_ids = []
        for title, sentences in it["context"]:
            did = _doc_id(title)
            sent_by_title[title] = sentences
            doc_ids.append(did)
            if did not in docs:
                docs[did] = {"id": did, "title": title,
                             "text": title + "\n\n" + "".join(sentences)}
        evidence = "".join(
            sent_by_title.get(title, [""] * (idx + 1))[idx]
            for title, idx in it.get("supporting_facts", [])
            if idx < len(sent_by_title.get(title, [])))
        answer = (it.get("answer") or "").strip()
        if not answer:
            continue
        questions.append({"question": it["question"].strip(), "answer": answer,
                          "alt_answers": [], "evidence": evidence,
                          "type": it.get("type") or "bridge",
                          "doc_ids": doc_ids, "scope_doc_id": None})
    write_json_atomic({"format": "noema-humanqa-v1", "gold_source": GOLD_SOURCE,
                       "about": ABOUT, "documents": list(docs.values()),
                       "questions": questions}, out)
    print(f"wrote {out} — {len(docs)} paragraphs, {len(questions)} questions")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "hotpot_dev_distractor_v1.json"))
    ap.add_argument("--download", action="store_true", help="fetch the official dev split first")
    ap.add_argument("--out", default=str(RAW_DIR / "s1-hotpotqa.json"))
    ap.add_argument("--max-questions", type=int, default=0, help="0 = keep all")
    args = ap.parse_args()

    src = Path(args.src)
    if args.download:
        src.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL} …")
        urllib.request.urlretrieve(URL, src)
    convert(src, Path(args.out), args.max_questions)


if __name__ == "__main__":
    main()
