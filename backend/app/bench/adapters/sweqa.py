"""SWE-QA -> noema-humanqa-v1.

SWE-QA (2025): 720 manually curated, validated natural-language questions over
15 real Python repositories at pinned commits — repository-level multi-hop by
design (avg 8.7 functions across 3.2 files per answer). The coding stage: can
retrieval navigate a codebase it did not index code-aware?

Corpus documents = one per .py source file (short ids keep the JSON small; the
title carries repo/path). Released questions name no files, so every question
carries its WHOLE repo's file list as doc_ids — the loader then admits a
question only when its entire repo fits the prepare cap, keeping corpora
repo-complete (a half-ingested repo would make questions unanswerable through
no fault of the retriever). No scope_doc_id: cross-file search is the test.
No evidence spans are released, so evidence-recall columns stay blank here.

Input: the SWE-QA-Bench checkout (Benchmark/*.jsonl + repo_commit.txt) plus the
pinned repo snapshots extracted side by side (see --repos-dir). --repos filters
which repositories to include (size control: GitHub caps files at 100MB).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.bench.adapters.util import write_json_atomic
from app.bench.store import RAW_DIR

GOLD_SOURCE = ("human (SWE-QA — 2025; manually curated + validated questions "
               "over 15 pinned real-world Python repositories)")
ABOUT = ("SWE-QA: repository-level questions over real codebases (Django, Flask, "
         "pytest…), answered in natural language and multi-hop across files by "
         "construction. One document per source file; a question enters the gold "
         "only when its whole repository fits the prepare cap.")

_MAX_FILE_BYTES = 200_000  # generated monsters (parser tables etc.) add no signal


def convert(bench_dir: Path, repos_dir: Path, out: Path,
            repos: list[str]) -> None:
    documents, questions = [], []
    for repo in repos:
        qa_file = bench_dir / "Benchmark" / f"{repo}.jsonl"
        repo_root = repos_dir / repo
        if not qa_file.exists() or not repo_root.is_dir():
            print(f"  skipping {repo}: missing questions or snapshot")
            continue
        file_ids = []
        for path in sorted(repo_root.rglob("*.py")):
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            rel = f"{repo}/{path.relative_to(repo_root)}"
            fid = f"f{len(documents)}"
            documents.append({"id": fid, "title": rel, "text": f"# {rel}\n\n{text}"})
            file_ids.append(fid)
        n = 0
        for line in qa_file.open(encoding="utf-8"):
            r = json.loads(line)
            if not (r.get("question") and r.get("answer")):
                continue
            questions.append({"question": r["question"].strip(),
                              "answer": str(r["answer"]).strip(),
                              "alt_answers": [], "evidence": "",
                              "type": repo, "doc_ids": file_ids,
                              "scope_doc_id": None})
            n += 1
        print(f"  {repo}: {len(file_ids)} files, {n} questions")
    write_json_atomic({"format": "noema-humanqa-v1", "gold_source": GOLD_SOURCE,
                       "about": ABOUT, "documents": documents,
                       "questions": questions}, out)
    print(f"wrote {out} — {len(documents)} files, {len(questions)} questions")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "SWE-QA-Bench-master"))
    ap.add_argument("--repos-dir", default=str(RAW_DIR / "raw" / "sweqa-repos"))
    ap.add_argument("--repos", required=True,
                    help="comma-separated repo names to include (size control)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    convert(Path(args.src), Path(args.repos_dir), Path(args.out),
            [r.strip() for r in args.repos.split(",") if r.strip()])


if __name__ == "__main__":
    main()
