"""Basel-FAQ (a GBS-QA-style reconstruction) -> noema-humanqa-v1.

GBS-QA (Sohn, Kwon & Choi, ECONLP 2021) was built from the BCBS Basel Framework:
questions market participants asked the Basel Committee, answered officially by
the BCBS and published as per-provision FAQs. The paper's 186 expert-revised
pairs were never publicly released, so this adapter rebuilds from the SAME
source, exactly as their methodology describes: crawl www.bis.org/basel_framework
(the /api/bcbs_standards + /api/bcbs_chapters JSON the site itself uses), take
the current in-force version of every chapter of the 14 standards, and keep each
FAQ verbatim — question from the market, answer from the BCBS.

Corpus documents = whole chapters (provisions numbered the way the framework
cites them, e.g. RBC30.12). Each FAQ is scoped to its chapter and its `evidence`
is the provision paragraph it hangs on. `type` is the surface form of the
question (binary / wh / how / conditional / other — the same axes GBS-QA
classified by hand).

Input: the crawl dump produced by `python -m app.bench.adapters.baselfaq --crawl`
(one polite request per chapter), or an existing dump via --src.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

from app.bench.adapters.util import question_form, strip_html, write_json_atomic
from app.bench.store import RAW_DIR

GOLD_SOURCE = ("human (BCBS Basel Framework FAQs — official BIS answers to market "
               "participants' questions; GBS-QA-style reconstruction)")
ABOUT = ("Official BCBS Basel Framework FAQs: questions market participants asked the Basel "
         "Committee during rule-making, answered formally by the BCBS — the same source the "
         "GBS-QA paper (ECONLP 2021) used, whose dataset was never released. Current in-force "
         "text of all 14 standards: whole chapters as documents (provisions numbered as the "
         "framework cites them, e.g. RBC30.12), each FAQ scoped to its chapter with the "
         "provision it annotates as evidence.")
_P_BLOCK = re.compile(r"<p\b.*?</p\s*>", re.I | re.S)


def crawl(out_path: Path) -> None:
    def get(url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; noema-bench)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    today = date.today().isoformat()
    dump = []
    for std in get("https://www.bis.org/api/bcbs_standards.json"):
        by_name: dict[str, list] = {}
        for ch in std["chapters"]:
            by_name.setdefault(ch["name"], []).append(ch)
        for name, versions in sorted(by_name.items()):
            live = [v for v in versions if v.get("in_force_at", "9999") <= today
                    and not (v.get("removed_at") and v["removed_at"] <= today)]
            if not live:
                continue
            cur = max(live, key=lambda v: (v["in_force_at"], v["id"]))
            time.sleep(0.7)
            full = get(f"https://www.bis.org/api/bcbs_chapters/{cur['id']}.json")
            dump.append({"standard": std["name"], "standard_title": std["title"],
                         "chapter": name, "chapter_title": cur.get("title", ""),
                         "id": cur["id"], "in_force_at": cur.get("in_force_at"), "data": full})
            print(f"{std['name']}{name} paras={len(full.get('paragraphs') or [])}", flush=True)
    out_path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")


def split_faq(faq_html: str) -> tuple[str, str] | None:
    blocks = [strip_html(b) for b in _P_BLOCK.findall(faq_html or "")]
    blocks = [b for b in blocks if b]
    if len(blocks) >= 2:
        return blocks[0], "\n\n".join(blocks[1:])
    text = strip_html(faq_html or "")
    if "?" in text:
        q, _, a = text.partition("?")
        if a.strip():
            return q.strip() + "?", a.strip()
    return None


def convert(dump: list) -> dict:
    documents, questions = [], []
    for ch in dump:
        doc_id = f"{ch['standard']}{ch['chapter']}"
        lines = [f"{doc_id} — {ch['chapter_title']} ({ch['standard_title']})"]
        faqs = []
        for para in ch["data"].get("paragraphs") or []:
            content = strip_html(para.get("content") or "")
            if not content:
                continue
            ref = f"{ch['standard']}{para['name']}" if not para.get("is_section_title") else ""
            lines.append(f"## {content}" if para.get("is_section_title") else f"{ref} {content}")
            for faq in para.get("faqs") or []:
                pair = split_faq(faq.get("text") or "")
                if pair:
                    faqs.append((ref or doc_id, content, *pair))
        if len(lines) < 2:
            continue
        documents.append({"id": doc_id, "title": f"{doc_id} — {ch['chapter_title']}",
                          "text": "\n\n".join(lines)})
        for ref, provision, q, a in faqs:
            questions.append({"question": q, "answer": a, "alt_answers": [],
                              "evidence": f"{ref} {provision}", "type": question_form(q),
                              "doc_ids": [doc_id], "scope_doc_id": doc_id})

    return {"format": "noema-humanqa-v1", "name": "basel-faq", "gold_source": GOLD_SOURCE,
            "about": ABOUT,
            "source_url": "https://www.bis.org/basel_framework/",
            "built_by": "app/bench/adapters/baselfaq.py",
            "documents": documents, "questions": questions}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(RAW_DIR / "raw" / "bcbs_chapters_raw.json"))
    ap.add_argument("--crawl", action="store_true", help="fetch the dump from bis.org first")
    ap.add_argument("--out", default=str(RAW_DIR / "basel-faq.json"))
    args = ap.parse_args()

    if args.crawl or not Path(args.src).exists():
        Path(args.src).parent.mkdir(parents=True, exist_ok=True)
        crawl(Path(args.src))
    data = convert(json.loads(Path(args.src).read_text(encoding="utf-8")))
    write_json_atomic(data, args.out)
    from collections import Counter
    print(f"{args.out}: {len(data['questions'])} FAQs, {len(data['documents'])} chapters")
    print("types:", dict(Counter(q["type"] for q in data["questions"])))


if __name__ == "__main__":
    main()
