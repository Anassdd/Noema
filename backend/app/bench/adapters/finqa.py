"""FinQA -> noema-humanqa-v1.

FinQA (Chen et al., EMNLP 2021): numerical multi-hop questions written by
financial experts over S&P 500 earnings-report pages — each page is prose AND a
table, and answering means cross-referencing both ("what is the change in X as a
percent of Y"). The evidence rows/sentences are expert-annotated (gold_inds).

Corpus documents = unique report pages (prose + the table rendered as a markdown
grid + prose). Each question is scoped to its page (scope_doc_id) — the dataset
asks about one filing page at a time, like FinanceBench. `type` splits by where
the evidence lives (table / text / table+text), so report slices show whether
table structure survives parsing, chunking and retrieval.

Input: dev.json / train.json from github.com/czyssrs/FinQA (public), via
--download (dev split) or --src.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from app.bench.adapters.util import write_json_atomic
from app.bench.store import RAW_DIR

URL = "https://raw.githubusercontent.com/czyssrs/FinQA/main/dataset/dev.json"

GOLD_SOURCE = ("human (FinQA — Chen et al. 2021; expert-written numerical QA over "
               "S&P 500 filing pages, expert-annotated evidence)")
ABOUT = ("FinQA dev: financial experts wrote numerical multi-hop questions over "
         "earnings-report pages (prose + table). Answers require reading the text, "
         "cross-referencing the table and computing — the jargon + tabular-structure "
         "stress test. Type slices: table / text / table+text evidence.")


def _table_md(table: list[list[str]]) -> str:
    if not table:
        return ""
    rows = ["| " + " | ".join(str(c).strip() for c in r) + " |" for r in table]
    rows.insert(1, "|" + "---|" * len(table[0]))
    return "\n".join(rows)


def _doc_id(page: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", page).strip("_").lower()


def _qtype(gold_inds: dict) -> str:
    keys = list(gold_inds or {})
    table = any(k.startswith("table") for k in keys)
    text = any(k.startswith("text") for k in keys)
    return "table+text" if table and text else "table" if table else "text"


def convert(src: Path, out: Path, max_questions: int = 0) -> None:
    items = json.loads(src.read_text(encoding="utf-8"))
    if max_questions:
        items = items[:max_questions]
    docs: dict[str, dict] = {}
    questions = []
    for it in items:
        page = it["id"].rsplit("-", 1)[0]  # "ADI/2009/page_49.pdf-2" -> the page
        did = _doc_id(page)
        if did not in docs:
            docs[did] = {"id": did, "title": page, "text": "\n\n".join(
                p for p in (" ".join(it.get("pre_text", [])),
                            _table_md(it.get("table", [])),
                            " ".join(it.get("post_text", []))) if p.strip())}
        qa = it.get("qa") or {}
        answer = str(qa.get("answer") or "").strip() or str(qa.get("exe_ans", "")).strip()
        if not qa.get("question") or not answer:
            continue
        alt = str(qa.get("exe_ans", "")).strip()
        gold_inds = qa.get("gold_inds") or {}
        questions.append({"question": qa["question"].strip(), "answer": answer,
                          "alt_answers": [alt] if alt and alt != answer else [],
                          "evidence": " ".join(str(v) for v in gold_inds.values()),
                          "type": _qtype(gold_inds),
                          "doc_ids": [did], "scope_doc_id": did})
    write_json_atomic({"format": "noema-humanqa-v1", "gold_source": GOLD_SOURCE,
                       "about": ABOUT, "documents": list(docs.values()),
                       "questions": questions}, out)
    print(f"wrote {out} — {len(docs)} filing pages, {len(questions)} questions")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "finqa_dev.json"))
    ap.add_argument("--download", action="store_true", help="fetch the official dev split first")
    ap.add_argument("--out", default=str(RAW_DIR / "s3-finqa.json"))
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
