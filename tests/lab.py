"""Noema Lab — an interactive playground for the pipeline steps.

Run it (from the repo root):
    backend/.venv/bin/python -m streamlit run tests/lab.py

Drop in a PDF, pick an engine (standard / OCR / Granite-Docling VLM), hit Run, and
watch the step behave: the page render next to the parsed Markdown, with timings,
legibility, and the canonical-structure counts. "Save to study" snapshots the run
into tests/results/study.md so messing around builds a kept report. Imports the
app's parse function read-only — it changes nothing in the product, and deleting
tests/ removes it without a trace.
"""

from __future__ import annotations

import io
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent           # tests/
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app import docling_parse  # noqa: E402

FIXTURES = ROOT / "fixtures" / "pdfs"
MYPDFS = ROOT / "myTestPDFs"            # drop your own PDFs here to test them
RESULTS = ROOT / "results"
STUDY = RESULTS / "study.md"
ASSETS = RESULTS / "study_assets"
REPORT = RESULTS / "docling_report.md"
SUITE = ROOT / "docling" / "run.py"


def render_pages(data: bytes, max_pages: int = 4):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    n = len(pdf)
    imgs = [pdf[i].render(scale=1.5).to_pil() for i in range(min(n, max_pages))]
    return imgs, n


def table_note(md: str) -> str:
    if "|" in md:
        return "Markdown table grid present"
    if "<!-- image -->" in md:
        return "region(s) classified as image (text may be lost)"
    return "no table detected"


def structure_summary(doc_dict: dict) -> dict:
    """Counts from the canonical DoclingDocument — what Markdown can't show."""
    return {
        "texts": len(doc_dict.get("texts", [])),
        "tables": len(doc_dict.get("tables", [])),
        "pictures": len(doc_dict.get("pictures", [])),
    }


ENGINE_CHOICES = {
    "Auto": "auto",
    "Standard (fast)": "standard",
    "Force OCR": "ocr",
    "Granite-Docling VLM": "vlm",
}


def save_to_study(entry: dict, imgs, md: str, note: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = "".join(c if c.isalnum() else "-" for c in entry["name"])[:40]
    folder = ASSETS / f"{stamp}_{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    if imgs:
        imgs[0].save(folder / "page1.png")
    (folder / "parsed.md").write_text(md, encoding="utf-8")

    rel = folder.relative_to(RESULTS)
    s = entry.get("struct", {})
    block = [
        f"\n## {datetime.now():%Y-%m-%d %H:%M} — `{entry['name']}`",
        "",
        f"- **Engine:** {entry['engine_used']} · **Legibility:** {entry['legibility']:.2f}",
        f"- **Pages:** {entry['pages']} · **Chars:** {entry['chars']} · "
        f"**Time:** {entry['secs']:.2f}s ({entry['per_page']:.2f}s/page)",
        f"- **Structure:** {s.get('texts', 0)} texts · {s.get('tables', 0)} tables · "
        f"{s.get('pictures', 0)} pictures · **Tables:** {table_note(md)}",
        f"- **Notes:** {note or '—'}",
        "",
        f"![page]({rel}/page1.png)" if imgs else "",
        f"\n_Parsed Markdown: `{rel}/parsed.md`_",
    ]
    header = "" if STUDY.exists() else "# Noema — parse study\n\nCurated runs from the lab.\n"
    with STUDY.open("a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write("\n".join(block) + "\n")


# ---- UI --------------------------------------------------------------------
st.set_page_config(page_title="Noema Lab", layout="wide")
st.title("Noema Lab")
st.caption("Interactive pipeline testbench · independent of the app")

with st.sidebar:
    st.header("Step")
    st.selectbox("Pipeline step", ["Parse — Docling"], index=0)

    st.header("Input")
    mode = st.radio("Source", ["Fixture", "Upload"], horizontal=True)
    data, name = None, None
    if mode == "Upload":
        up = st.file_uploader("Drop a PDF", type="pdf")
        if up:
            data, name = up.getvalue(), up.name
    else:
        pool = {}
        for base, tag in [(FIXTURES, "fixtures"), (MYPDFS, "mine")]:
            if base.exists():
                for p in sorted(base.glob("*.pdf")):
                    pool[f"{tag}/{p.name}"] = p
        if pool:
            choice = st.selectbox("File", list(pool))
            data, name = pool[choice].read_bytes(), pool[choice].name
        else:
            st.info("No PDFs — run make_fixtures.py or drop files in tests/myTestPDFs/")

    engine_label = st.radio(
        "Engine",
        list(ENGINE_CHOICES),
        help="Auto runs Standard, escalating to OCR if the text layer is garbled. "
        "Force OCR rebuilds text from pixels (broken-font / scanned). VLM "
        "(Granite-Docling) reads the page like an image — best for math, tables, "
        "and broken fonts, but slower.",
    )
    engine = ENGINE_CHOICES[engine_label]
    formulas = st.checkbox(
        "Decode formulas → LaTeX",
        value=False,
        help="Transcribe formula images to LaTeX (else they show as "
        "<!-- formula-not-decoded -->). Ignored by VLM, which does it natively.",
    )
    run = st.button("▶ Run parse", type="primary", use_container_width=True, disabled=data is None)

if run and data is not None:
    with st.spinner(f"parsing with {engine}… (first run loads models)"):
        t0 = time.perf_counter()
        try:
            doc = docling_parse.parse_pdf(data, name, engine=engine, formulas=formulas)
            md, pages, leg = doc.markdown, doc.pages, doc.legibility
            used, struct, err = doc.engine, structure_summary(doc.doc_dict), None
        except docling_parse.ParseError as exc:
            md, pages, leg, used, struct, err = "", 0, 0.0, engine, {}, str(exc)
        secs = time.perf_counter() - t0
        try:
            imgs, npages = render_pages(data)
        except Exception:
            imgs, npages = [], pages
    st.session_state["last"] = dict(
        name=name, engine=engine, engine_used=used, formulas=formulas, md=md,
        pages=pages or npages, chars=len(md), secs=secs,
        per_page=secs / max(pages or npages, 1), legibility=leg,
        undecoded=md.count("<!-- formula-not-decoded -->"), struct=struct,
        err=err, imgs=imgs,
    )

last = st.session_state.get("last")
if last:
    if last["err"]:
        st.error(f"Parse rejected: {last['err']}")
    s = last.get("struct", {})
    c = st.columns(5)
    c[0].metric("Pages", last["pages"])
    c[1].metric("Chars", f"{last['chars']:,}")
    c[2].metric("Time", f"{last['secs']:.2f}s")
    c[3].metric("Per page", f"{last['per_page']:.2f}s")
    c[4].metric("Legibility", f"{last['legibility']:.2f}")
    st.caption(
        f"engine: **{last.get('engine_used', '?')}** · {table_note(last['md'])} · "
        f"canonical: {s.get('texts', 0)} texts / {s.get('tables', 0)} tables / "
        f"{s.get('pictures', 0)} pictures (DoclingDocument)"
    )
    if last["md"] and last["legibility"] < 0.6:
        st.warning(
            f"⚠ The text layer looks garbled (legibility {last['legibility']:.2f}) — "
            "likely a broken-font / LaTeX PDF. Switch the Engine to **Force OCR** or "
            "**Granite-Docling VLM** and re-run."
        )
    if last.get("undecoded"):
        st.warning(
            f"⚠ {last['undecoded']} formula(s) not decoded "
            "(`<!-- formula-not-decoded -->`). Tick **Decode formulas → LaTeX**, or "
            "use the **VLM** engine."
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Input")
        for img in last["imgs"]:
            st.image(img, use_container_width=True)
        if not last["imgs"]:
            st.info("No page preview.")
    with right:
        st.subheader("Parsed Markdown")
        if last["md"]:
            with st.expander("raw", expanded=False):
                st.code(last["md"], language="markdown")
            st.markdown(last["md"])
        else:
            st.info("Nothing parsed.")

    st.divider()
    note = st.text_input("Note for the study (what were you testing?)")
    if st.button("＋ Save to study"):
        save_to_study(last, last["imgs"], last["md"], note)
        st.success(f"Saved to {STUDY.relative_to(ROOT.parent)}")

# ---- Benchmark suite + conserved report ------------------------------------
st.divider()
st.subheader("Edge-case suite & report")
if st.button("Run full edge-case suite"):
    with st.spinner("running suite…"):
        subprocess.run([sys.executable, str(SUITE)], capture_output=True, text=True)
    st.success("Done — report refreshed below.")
if REPORT.exists():
    st.markdown(REPORT.read_text(encoding="utf-8"))
if STUDY.exists():
    with st.expander("📓 Saved study log"):
        st.markdown(STUDY.read_text(encoding="utf-8"))
