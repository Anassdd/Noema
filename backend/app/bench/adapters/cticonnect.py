"""CTIConnect -> noema-humanqa-v1.

CTIConnect (Peng Gao lab, 2025; data CC-BY-4.0): 1,859 expert-curated QA pairs
over heterogeneous cyber-threat intelligence — the security stage's scored
benchmark. Three families, kept as `type` slices via their 9 task codes:

- entity_linking (rcm/atd/esd/wim): map a described weakness/technique to the
  right CVE/CWE/CAPEC/ATT&CK entry — relationship traversal across taxonomies.
- entity_attribution (ata/vca): read a vendor-report excerpt, attribute it to
  the ATT&CK technique(s) or CVE(s) it describes.
- multi_doc_synthesis (tap/mla/csc): synthesize across several vendor reports
  (actor alias resolution, campaign timelines) — graded free-text gold.

Corpus = everything the benchmark ships: the four knowledge bases (ATT&CK
techniques, CWE, CAPEC, and their 3,011-entry CVE scope) rendered from their
JSON `contents` into readable text, plus the 321 preprocessed vendor reports.
Questions are corpus-wide (no scope_doc_id) — cross-source linking IS the test.
The prose `answer` is the judged gold; the ground-truth ID (e.g. "CWE-384")
rides as an alt answer so a bare-ID reply also scores. `evidence` = the target
entry's text when the ground truth names one, else the reference answer.

Input: the CTIConnect repo checkout (--src), e.g. from
github.com/peng-gao-lab/CTIConnect (data license CC-BY-4.0 — attribute in
reports).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.bench.adapters.util import write_json_atomic
from app.bench.store import RAW_DIR

GOLD_SOURCE = ("human (CTIConnect — Peng Gao lab 2025, expert-curated CTI QA; "
               "data CC-BY-4.0)")
ABOUT = ("CTIConnect: expert-curated QA over cyber-threat intelligence — linking "
         "descriptions to CVE/CWE/CAPEC/ATT&CK entries, attributing vendor-report "
         "excerpts to techniques, and synthesizing across reports. Corpus = the "
         "shipped knowledge bases + 321 vendor reports. The graph stress test: "
         "overlapping terminology, strict relationships.")

_SKIP_KEYS = {"external_references", "x_mitre_modified_by_ref", "created_by_ref",
              "object_marking_refs", "id", "type", "spec_version", "references"}


def _render(value, depth: int = 0) -> list[str]:
    """JSON contents -> readable indented lines, keeping descriptive fields and
    dropping STIX bookkeeping (refs, GUIDs)."""
    lines: list[str] = []
    pad = "  " * depth
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _SKIP_KEYS or k.endswith("_ref"):
                continue
            if isinstance(v, (dict, list)):
                sub = _render(v, depth + 1)
                if sub:
                    lines.append(f"{pad}{k}:")
                    lines.extend(sub)
            elif isinstance(v, str) and len(v.strip()) > 2:
                lines.append(f"{pad}{k}: {v.strip()}")
    elif isinstance(value, list):
        for v in value:
            lines.extend(_render(v, depth))
    elif isinstance(value, str) and len(value.strip()) > 2:
        lines.append(f"{pad}{value.strip()}")
    return lines


def _doc_id(kind: str, native: str) -> str:
    return f"{kind}_" + re.sub(r"[^A-Za-z0-9]+", "_", native).strip("_").lower()


def _load_corpus(src: Path):
    docs, by_native = [], {}

    def add(kind: str, native: str, title: str, text: str):
        did = _doc_id(kind, native)
        if did in by_native:
            return
        by_native[native.upper()] = did
        by_native[did] = did
        docs.append({"id": did, "title": f"{native} — {title}" if title else native,
                     "text": text})

    # The KBs store bare numbers for CWE/CAPEC ("79") while ground truths use the
    # canonical form ("CWE-79") — canonicalize so lookups and doc titles agree.
    kb_native = {"cve": ("cve_id", ""), "mitre": ("mitre_id", ""),
                 "cwe": ("cwe_id", "CWE-"), "capec": ("capec_id", "CAPEC-")}
    for kind, (native_key, prefix) in kb_native.items():
        for line in (src / "corpus_kb" / f"{kind}.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            native = str(r.get(native_key) or r.get("title") or r["id"])
            if prefix and not native.upper().startswith(prefix):
                native = prefix + native
            try:
                body = "\n".join(_render(json.loads(r["contents"])))
            except (ValueError, TypeError):
                body = str(r.get("contents") or "")
            add(kind, native, str(r.get("title") or ""), f"{native}\n\n{body}")

    for line in (src / "corpus_reports" / "preprocessed_reports.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        add("blog", f"BLOG-{r['id']}", str(r.get("title") or ""),
            f"{r.get('title') or ''}\n\n{r.get('preprocessed') or ''}")
    return docs, by_native


def convert(src: Path, out: Path) -> None:
    docs, by_native = _load_corpus(src)
    text_of = {d["id"]: d["text"] for d in docs}

    questions, missing_targets = [], 0
    for qa_file in sorted(src.glob("data/*/*.jsonl")):
        for line in qa_file.open(encoding="utf-8"):
            r = json.loads(line)
            gt = r.get("ground_truth") or {}
            target_ids = [t for t in
                          ([gt.get("target_id")] if gt.get("target_id")
                           else gt.get("target_ids") or [])]
            target_docs = [by_native[t.upper()] for t in target_ids
                           if t and t.upper() in by_native]
            missing_targets += sum(1 for t in target_ids
                                   if t and t.upper() not in by_native)

            source = r.get("source") or {}
            src_natives = ([source.get("source_id")] if source.get("source_id")
                           else source.get("blog_ids") or [])
            src_docs = [by_native[s.upper()] for s in src_natives
                        if s and s.upper() in by_native]

            evidence = ""
            if target_docs:
                evidence = text_of[target_docs[0]][:2000]
            elif gt.get("reference_answer"):
                evidence = str(gt["reference_answer"])

            questions.append({
                "question": r["question"].strip(),
                "answer": str(r.get("answer") or "").strip(),
                "alt_answers": [", ".join(target_ids)] if target_ids else [],
                "evidence": evidence,
                "type": r.get("task") or r.get("category") or "cti",
                "doc_ids": sorted(set(src_docs + target_docs)),
                "scope_doc_id": None,
            })

    write_json_atomic({"format": "noema-humanqa-v1", "gold_source": GOLD_SOURCE,
                       "about": ABOUT, "documents": docs,
                       "questions": questions}, out)
    print(f"wrote {out} — {len(docs)} corpus entries, {len(questions)} questions "
          f"({missing_targets} ground-truth ids not found in the shipped KBs)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "CTIConnect-main"))
    ap.add_argument("--out", default=str(RAW_DIR / "s4-cticonnect.json"))
    args = ap.parse_args()
    convert(Path(args.src), Path(args.out))


if __name__ == "__main__":
    main()
