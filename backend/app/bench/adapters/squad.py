"""SQuAD v1.1 (dev split) -> noema-humanqa-v1.

SQuAD (Rajpurkar et al., EMNLP 2016) is crowdsourced Wikipedia QA: every answer
is a span a human marked in the article, and the dev split carries up to three
independent annotator answers per question (they become `alt_answers`). General
knowledge, not domain-specific — which is exactly its role here: the MECHANISM
smoke set. It is also the densest corpus we have (~50 questions per ~5k-token
article), so even a tiny prepare cap yields hundreds of gold questions.

Corpus documents = whole articles (title + paragraphs). Each question is scoped
to its article (`scope_doc_id`) — SQuAD questions are written against one page
("When did the war end?") and are unfair as whole-corpus searches. `evidence` is
the paragraph the answer span lives in, so evidence recall is verbatim-checkable.

Input: the official dev-v1.1.json (public, ~5 MB), via --download or --src.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from app.bench.adapters.util import question_form, write_json_atomic
from app.bench.store import RAW_DIR

URL = "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v1.1.json"

GOLD_SOURCE = ("human (SQuAD v1.1 dev — Rajpurkar et al. 2016; crowdsourced "
               "Wikipedia QA, up to 3 annotator answers per question)")
ABOUT = ("SQuAD v1.1 dev split: general-knowledge Wikipedia articles with "
         "crowdsourced span answers. The mechanism smoke set — dense enough that "
         "a small prepare cap still yields hundreds of human gold questions.")


def _doc_id(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()


def convert(src: Path, out: Path) -> None:
    data = json.loads(src.read_text(encoding="utf-8"))["data"]
    documents, questions = [], []
    for article in data:
        did = _doc_id(article["title"])
        contexts = [p["context"] for p in article["paragraphs"]]
        title = article["title"].replace("_", " ")
        documents.append({"id": did, "title": title,
                          "text": title + "\n\n" + "\n\n".join(contexts)})
        for para in article["paragraphs"]:
            for qa in para["qas"]:
                answers = []
                for a in qa.get("answers", []):
                    t = (a.get("text") or "").strip()
                    if t and t not in answers:
                        answers.append(t)
                if not answers:
                    continue
                questions.append({"question": qa["question"].strip(),
                                  "answer": answers[0],
                                  "alt_answers": answers[1:],
                                  "evidence": para["context"],
                                  "type": question_form(qa["question"]),
                                  "doc_ids": [did], "scope_doc_id": did})
    write_json_atomic({"format": "noema-humanqa-v1", "gold_source": GOLD_SOURCE,
                       "about": ABOUT, "documents": documents,
                       "questions": questions}, out)
    print(f"wrote {out} — {len(documents)} articles, {len(questions)} questions")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "dev-v1.1.json"))
    ap.add_argument("--download", action="store_true", help="fetch the official dev split first")
    ap.add_argument("--out", default=str(RAW_DIR / "squad-general.json"))
    args = ap.parse_args()

    src = Path(args.src)
    if args.download:
        src.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {URL} …")
        urllib.request.urlretrieve(URL, src)
    convert(src, Path(args.out))


if __name__ == "__main__":
    main()
