"""FinanceBench (Patronus AI) -> noema-humanqa-v1.

Input: the open-source release at github.com/patronus-ai/financebench —
financebench_open_source.jsonl (150 QA), financebench_document_information.jsonl
(filing metadata), and the pdfs/ directory (the SEC filings the questions cite;
only the 84 filings the 150 questions reference are needed).

Documents are the FULL filings, text-extracted locally with pypdfium2 (no OCR:
SEC filings carry a digital text layer; tables flatten roughly but figures
survive). Each question is scoped to its one filing (scope_doc_id), matching how
FinanceBench is meant to be evaluated, and keeps the human evidence excerpts so
evidence metrics work. `type` = FinanceBench's question_type (metrics-generated /
domain-relevant / novel-generated).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pypdfium2 as pdfium

from app.bench.adapters.util import write_json_atomic
from app.bench.store import RAW_DIR

GOLD_SOURCE = ("human (FinanceBench — Islam et al. 2023, Patronus AI; "
               "150-question open-source set)")
ABOUT = ("FinanceBench (Patronus AI, 2023): financial-analyst questions about real SEC "
         "filings (10-K, 10-Q, 8-K, earnings releases), written and answered by human "
         "annotators with evidence excerpts and page numbers — so evidence metrics work "
         "end-to-end. The open-source set: 150 questions (50 metrics-generated, 50 "
         "domain-relevant, 50 novel) over 84 filings ingested whole, each question scoped "
         "to its own filing.")


def pdf_text(path: Path) -> str:
    doc = pdfium.PdfDocument(str(path))
    pages = []
    for page in doc:
        pages.append(page.get_textpage().get_text_bounded())
    return "\n\n".join(p.strip() for p in pages if p and p.strip())


def convert(qa_path: Path, info_path: Path, pdf_dir: Path) -> dict:
    qa = [json.loads(line) for line in qa_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    info = {row["doc_name"]: row for row in
            (json.loads(line) for line in info_path.read_text(encoding="utf-8").splitlines() if line.strip())}

    documents, missing = [], []
    for doc_name in sorted({q["doc_name"] for q in qa}):
        pdf = pdf_dir / f"{doc_name}.pdf"
        if not pdf.exists():
            missing.append(doc_name)
            continue
        meta = info.get(doc_name, {})
        title = f"{meta.get('company', doc_name)} {meta.get('doc_period', '')} {meta.get('doc_type', '')}".strip()
        text = pdf_text(pdf)
        if len(text) < 5000:
            missing.append(f"{doc_name} (extraction too thin: {len(text)} chars)")
            continue
        documents.append({"id": doc_name, "title": title, "text": f"{title}\n\n{text}"})

    have = {d["id"] for d in documents}
    questions = []
    for q in qa:
        if q["doc_name"] not in have:
            continue
        evidence = "\n\n".join(e.get("evidence_text", "").strip()
                               for e in q.get("evidence", []) if e.get("evidence_text", "").strip())
        questions.append({"question": q["question"].strip(), "answer": str(q["answer"]).strip(),
                          "alt_answers": [], "evidence": evidence, "type": q["question_type"],
                          "doc_ids": [q["doc_name"]], "scope_doc_id": q["doc_name"]})

    return {"format": "noema-humanqa-v1", "name": "financebench", "gold_source": GOLD_SOURCE,
            "about": ABOUT,
            "source_url": "https://github.com/patronus-ai/financebench",
            "built_by": "app/bench/adapters/financebench.py",
            "documents": documents, "questions": questions}, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qa", default=str(RAW_DIR / "raw" / "financebench_open_source.jsonl"))
    ap.add_argument("--docinfo", default=str(RAW_DIR / "raw" / "financebench_document_information.jsonl"))
    ap.add_argument("--pdf-dir", default=str(RAW_DIR / "raw" / "financebench_pdfs"))
    ap.add_argument("--out", default=str(RAW_DIR / "financebench.json"))
    args = ap.parse_args()

    data, missing = convert(Path(args.qa), Path(args.docinfo), Path(args.pdf_dir))
    write_json_atomic(data, args.out)
    print(f"{args.out}: {len(data['questions'])} questions, {len(data['documents'])} filings")
    if missing:
        print(f"MISSING ({len(missing)}):", ", ".join(missing))


if __name__ == "__main__":
    main()
