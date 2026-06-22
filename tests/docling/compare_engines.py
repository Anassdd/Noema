"""Compare Docling parse configs on one PDF — validate the SOTA choice on your
own corpus. Measures legibility (broken-font detection), formula decoding, and
speed. Writes tests/results/engine_comparison.md.

    backend/.venv/bin/python tests/docling/compare_engines.py [path/to.pdf]
"""

from __future__ import annotations

import platform
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app import docling_parse  # noqa: E402

DEFAULT = ROOT / "myTestPDFs" / "resume_af.pdf"
RESULTS = ROOT / "results"

# (engine, formulas, label)
CONFIGS = [
    ("standard", False, "standard"),
    ("standard", True, "standard+formulas"),
    ("ocr", True, "ocr+formulas"),
    ("vlm", False, "vlm (granite-docling)"),
]

_LATEX = ("\\frac", "\\sum", "\\int", "\\sqrt", "\\le", "\\ge", "\\alpha", "$")


def _formula_stats(md: str):
    placeholders = md.count("<!-- formula-not-decoded -->")
    has_latex = any(tok in md for tok in _LATEX)
    return placeholders, has_latex


def run(pdf: Path, configs=CONFIGS):
    data = pdf.read_bytes()
    rows = []
    for engine, formulas, label in configs:
        print(f"running {label}…", flush=True)
        t = time.perf_counter()
        try:
            d = docling_parse.parse_pdf(data, pdf.name, engine=engine, formulas=formulas)
            ph, latex = _formula_stats(d.markdown)
            rows.append({
                "label": label, "ok": True, "pages": d.pages, "chars": d.chars,
                "leg": d.legibility, "secs": time.perf_counter() - t,
                "ph": ph, "latex": latex, "head": " ".join(d.markdown[:280].split()),
            })
        except Exception as exc:
            rows.append({"label": label, "ok": False, "secs": time.perf_counter() - t,
                         "err": str(exc)[:160]})
        print(f"  {label}: {rows[-1]['secs']:.1f}s", flush=True)
    return rows


def report(pdf: Path, rows):
    lines = [
        f"# Parse-engine comparison — `{pdf.name}`",
        "",
        f"_{datetime.now():%Y-%m-%d %H:%M} · {platform.machine()} CPU · "
        f"{pdf.stat().st_size // 1024} KB_",
        "",
        "| Config | Pages | Chars | Legibility | Formula-boxes | LaTeX? | Time | s/page |",
        "| --- | ---: | ---: | ---: | ---: | :---: | ---: | ---: |",
    ]
    for r in rows:
        if r["ok"]:
            per = r["secs"] / max(r["pages"], 1)
            lines.append(
                f"| `{r['label']}` | {r['pages']} | {r['chars']} | {r['leg']:.2f} | "
                f"{r['ph']} | {'yes' if r['latex'] else 'no'} | {r['secs']:.1f}s | {per:.1f}s |"
            )
        else:
            lines.append(f"| `{r['label']}` | — | — | — | — | — | {r['secs']:.1f}s | **FAILED** |")
    lines += [
        "",
        "_Legibility < 0.6 = garbled text layer. Formula-boxes = undecoded "
        "`<!-- formula-not-decoded -->` placeholders (lower is better)._",
        "",
        "## Output head (first ~280 chars)",
        "",
    ]
    for r in rows:
        if r["ok"]:
            lines += [f"**`{r['label']}`** — legibility {r['leg']:.2f}, "
                      f"{r['ph']} undecoded formulas", "", f"> {r['head']}", ""]
        else:
            lines += [f"**`{r['label']}`** — failed: {r['err']}", ""]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "engine_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    report(pdf, run(pdf))
