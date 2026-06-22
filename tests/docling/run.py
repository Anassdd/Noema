"""Run the Docling parse step over every fixture, time it, and score it.

Writes tests/results/docling_report.md (the table + findings), each fixture's
parsed Markdown to results/markdown/, and a PNG render of each input to
results/screenshots/. Independent of cwd — it locates the backend itself.
"""

from __future__ import annotations

import platform
import sys
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # tests/
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import docling_parse  # noqa: E402

PDFS = ROOT / "fixtures" / "pdfs"
RESULTS = ROOT / "results"
MD_OUT = RESULTS / "markdown"
SHOTS = RESULTS / "screenshots"
for d in (MD_OUT, SHOTS):
    d.mkdir(parents=True, exist_ok=True)

# (name, source, validates, expect, engine)  — expect: "ok" | "error" | "info"
CASES = [
    ("simple", "simple.pdf", "Plain digital text — baseline", "ok", "standard"),
    ("multipage", "multipage.pdf", "Page count across pages", "ok", "standard"),
    ("headings", "headings.pdf", "Structure -> Markdown headings", "ok", "standard"),
    ("table", "table.pdf", "Table reconstruction", "ok", "standard"),
    ("long", "long.pdf", "Throughput on a bigger doc", "ok", "standard"),
    ("empty", "empty.pdf", "Blank page -> clean error", "error", "standard"),
    ("scanned", "scanned.pdf", "Image-only page -> OCR engine", "info", "ocr"),
    ("not_a_pdf", b"This is plainly not a PDF file at all.", "Garbage bytes rejected", "error", "standard"),
    ("truncated", "TRUNCATE:simple.pdf", "Corrupted PDF rejected", "error", "standard"),
]


def load_bytes(source) -> bytes:
    if isinstance(source, bytes):
        return source
    if source.startswith("TRUNCATE:"):
        return (PDFS / source.split(":", 1)[1]).read_bytes()[:300]
    return (PDFS / source).read_bytes()


def screenshot(source, name) -> None:
    if not isinstance(source, str) or source.startswith("TRUNCATE:"):
        return
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(PDFS / source))
        if len(pdf) == 0:
            return
        pdf[0].render(scale=1.4).to_pil().save(SHOTS / f"{name}.png")
    except Exception:
        pass  # screenshots are a nicety, never fail the run on them


def note_for(name, md, pages, secs) -> str:
    if name == "table":
        if "|" in md and "HippoRAG-2" in md:
            return "table -> Markdown grid: yes"
        if "<!-- image -->" in md:
            return "table region classified as IMAGE — text lost"
        return "table not reconstructed"
    if name == "headings":
        return f"{md.count('#')} Markdown heading marks"
    if name in ("multipage", "long"):
        per = secs / pages if pages else 0
        return f"{pages} pages, {per:.2f}s/page"
    if name == "scanned":
        return f"OCR produced {len(md)} chars" if md else "no text recovered"
    if name == "simple":
        return f"{len(md)} chars"
    return ""


def run_case(name, source, validates, expect, engine="standard"):
    data = load_bytes(source)
    t0 = time.perf_counter()
    md, pages, error = "", 0, None
    try:
        doc = docling_parse.parse_pdf(data, f"{name}.pdf", engine=engine)
        md, pages = doc.markdown, doc.pages
    except docling_parse.ParseError as exc:
        error = str(exc)
    secs = time.perf_counter() - t0

    if md:
        (MD_OUT / f"{name}.md").write_text(md, encoding="utf-8")
    screenshot(source, name)

    got = "error" if error else "ok"
    if expect == "info":
        result = "ℹ︎ " + (got)
    else:
        result = "PASS" if got == expect else "FAIL"

    return {
        "name": name, "validates": validates, "expect": expect,
        "pages": pages, "chars": len(md), "secs": secs,
        "result": result, "note": note_for(name, md, pages, secs),
        "error": error,
    }


def main():
    print("building Docling converter (one-time model load)…", flush=True)
    t = time.perf_counter()
    docling_parse._get_converter("standard")
    cold = time.perf_counter() - t
    print(f"converter ready in {cold:.1f}s\n", flush=True)

    rows = []
    for case in CASES:
        r = run_case(*case)
        rows.append(r)
        print(f"  {r['result']:>5}  {r['name']:<10} {r['secs']:6.2f}s  {r['note']}", flush=True)

    write_report(rows, cold)
    passed = sum(1 for r in rows if r["result"] == "PASS")
    total = sum(1 for r in rows if r["expect"] != "info")
    print(f"\n{passed}/{total} pass-fail cases passed. Report: {RESULTS/'docling_report.md'}")


def write_report(rows, cold):
    by = {r["name"]: r for r in rows}
    long = by.get("long", {})
    steady = long["secs"] / long["pages"] if long.get("pages") else 0  # pure-text, representative
    first = by.get("simple", {}).get("secs", 0)  # first parse incl. JIT/model warmup
    scan = by.get("scanned", {})

    lines = [
        "# Docling parse — test report",
        "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M} · "
        f"docling {version('docling')} · Python {platform.python_version()} · "
        f"{platform.machine()} CPU_",
        "",
        "| Case | Validates | Pages | Chars | Time | Result | Notes |",
        "| --- | --- | ---: | ---: | ---: | :---: | --- |",
    ]
    for r in rows:
        lines.append(
            f"| `{r['name']}` | {r['validates']} | {r['pages'] or '—'} | "
            f"{r['chars'] or '—'} | {r['secs']:.2f}s | {r['result']} | {r['note']} |"
        )

    lines += [
        "",
        "## Speed & efficiency",
        "",
        f"- **Cold start (one-time per process):** {cold:.1f}s to build the converter, "
        f"then the first parse adds ~{first:.1f}s of warmup.",
        f"- **Steady-state (digital text):** {steady:.2f}s/page (the {long.get('pages','?')}-page doc).",
        f"- **OCR pages cost more:** the scanned page took {scan.get('secs',0):.1f}s for 1 page.",
        "- Runs on **CPU**; the per-page cost is the layout model on each page render.",
        "",
        "## Findings",
        "",
    ]
    findings = derive_findings(rows)
    lines += [f"- {f}" for f in findings]
    lines.append("")
    RESULTS.joinpath("docling_report.md").write_text("\n".join(lines), encoding="utf-8")


def derive_findings(rows):
    by = {r["name"]: r for r in rows}
    out = []
    tnote = by.get("table", {}).get("note", "")
    if "grid: yes" in tnote:
        out.append("Tables reconstruct into Markdown grids.")
    elif "IMAGE" in tnote:
        out.append(
            "On the **synthetic** vector table, Docling classified the region as an image "
            "(`<!-- image -->`) and dropped the text — a silent-content-loss failure mode. "
            "Validate on a real research-paper table before judging; likely a fixture artifact."
        )
    else:
        out.append("Table not reconstructed — investigate.")
    sc = by.get("scanned", {})
    if sc.get("chars"):
        out.append(
            f"OCR is **opt-in** (off by default for speed); with `engine='ocr'` the "
            f"image-only page yielded {sc['chars']} chars."
        )
    else:
        out.append("OCR (`engine='ocr'`) recovered no text from the image-only page.")
    errs = [r["name"] for r in rows if r["expect"] == "error" and r["result"] == "PASS"]
    out.append(f"Bad input is rejected cleanly (no crash): {', '.join(errs) or 'none'}.")
    out.append(
        "Cold start (model load) dominates a single parse — fine for batch ingestion, a "
        "one-time cost per process. First run downloads models (layout from HuggingFace; "
        "OCR models from ModelScope only when OCR is on) — a prod-network risk to pre-stage."
    )
    out.append("Not yet tested: math→LaTeX, multi-column reading order, encrypted PDFs.")
    return out


if __name__ == "__main__":
    main()
