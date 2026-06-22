"""Noema Lab — Vision PDF parser testbench.

Drop ANY PDF (drawings, tables, math, scans, broken fonts) and watch the parser
work: each page rendered on the left, the vision model's Markdown + LaTeX on the
right (formulas rendered), with timing and token cost. Record what you observe —
wins and fails accumulate into a "resume" at the bottom (tests/results/test_log.json).

Independent of the app; imports the parser read-only. Parsing runs through the
provider abstraction, so this uses whatever `.env` points at (OpenAI on the Mac).

    backend/.venv/bin/python -m streamlit run tests/lab.py

Heads-up: each page is a vision-model call (a few cents). Cap "Pages to parse".
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.parsing import vision  # noqa: E402

MYPDFS = ROOT / "myTestPDFs"
LOG = ROOT / "results" / "test_log.json"

_RATES = {"gpt-4o": (2.5, 10.0), "gpt-4o-mini": (0.15, 0.6)}  # $/1M tok, ballpark
_VERDICT = {"win": "✅", "fail": "❌", "partial": "⚠️"}


# ---- test log ---------------------------------------------------------------
def load_log() -> list[dict]:
    if LOG.exists():
        try:
            return json.loads(LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def add_result(pdf: str, scope: str, verdict: str, note: str) -> None:
    entries = load_log()
    entries.insert(0, {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pdf": pdf, "scope": scope, "verdict": verdict, "note": note,
    })
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


# ---- markdown + LaTeX rendering --------------------------------------------
def _normalize_math(md: str) -> str:
    md = re.sub(r"\\\((.+?)\\\)", r"$\1$", md, flags=re.S)      # \( .. \) -> $ .. $
    md = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", md, flags=re.S)    # \[ .. \] -> $$ .. $$
    return md


def render_markdown(md: str) -> None:
    """Render text+LaTeX via normal st.markdown (KaTeX works), and HTML tables via
    unsafe_allow_html — splitting them so the two don't fight (the LaTeX-not-rendering
    bug came from unsafe_allow_html being on for the whole string)."""
    md = _normalize_math(md)
    for part in re.split(r"(<table[\s\S]*?</table>)", md, flags=re.I):
        if not part.strip():
            continue
        if part.lstrip().lower().startswith("<table"):
            st.markdown(part, unsafe_allow_html=True)
        else:
            st.markdown(part)


def cost_estimate(model: str, p_tok: int, c_tok: int):
    rate = _RATES.get((model or "").split("/")[-1])
    return None if not rate else p_tok / 1e6 * rate[0] + c_tok / 1e6 * rate[1]


def render_page_images(data: bytes, scale: float, max_pages):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    total = len(pdf)
    count = total if max_pages is None else min(total, max_pages)
    return [pdf[i].render(scale=scale).to_pil() for i in range(count)], total


# ---- UI ---------------------------------------------------------------------
st.set_page_config(page_title="Noema Lab — Vision Parser", layout="wide")
st.title("Noema Lab — Vision PDF Parser")
st.caption(
    f"provider: **{settings.provider}** · default parse model: **{settings.parse_model}** "
    "· renders pages locally, transcribes via the vision model · independent of the app"
)

with st.sidebar:
    st.header("Input")
    src = st.radio("Source", ["Upload", "myTestPDFs"], horizontal=True)
    data, name = None, None
    if src == "Upload":
        up = st.file_uploader("Drop a PDF", type="pdf")
        if up:
            data, name = up.getvalue(), up.name
    else:
        pdfs = sorted(MYPDFS.glob("*.pdf")) if MYPDFS.exists() else []
        if pdfs:
            choice = st.selectbox("File", [p.name for p in pdfs])
            data, name = (MYPDFS / choice).read_bytes(), choice
        else:
            st.info("Drop PDFs into tests/myTestPDFs/")

    st.header("Settings")
    model = st.text_input("Vision model", value=settings.parse_model)
    max_pages = st.number_input("Pages to parse (0 = all)", min_value=0, value=2, step=1)
    scale = st.slider("Render scale (~72 DPI × this)", 1.0, 4.0, 2.0, 0.5)
    detail = st.selectbox(
        "Vision detail", ["high", "auto", "low"], index=0,
        help="high = max tiling (better for small/dense text); low = cheapest. "
        "A/B this on the stress pages.",
    )
    routing = st.selectbox(
        "Routing", ["auto", "vision"], index=0,
        help="auto = clean prose pages use the FREE text layer (no vision call); "
        "vision = force the model on every page.",
    )
    run = st.button("▶ Parse", type="primary", width="stretch", disabled=data is None)

if run and data is not None:
    mp = None if max_pages == 0 else int(max_pages)
    with st.spinner(f"rendering + transcribing with {model}…"):
        t0 = time.perf_counter()
        try:
            doc = vision.parse_pdf(
                data, name, model=model or None, scale=scale, detail=detail,
                max_pages=mp, mode=routing,
            )
            err = None
        except Exception as exc:
            doc, err = None, str(exc)
        secs = time.perf_counter() - t0
        try:
            imgs, _ = render_page_images(data, scale, mp)
        except Exception:
            imgs = []
    st.session_state["last"] = {
        "name": name, "doc": doc, "err": err, "secs": secs, "imgs": imgs, "detail": detail,
    }

last = st.session_state.get("last")
if last:
    if last["err"]:
        st.error(f"Parse failed: {last['err']}")
    doc = last["doc"]
    if doc:
        cost = cost_estimate(doc.model, doc.prompt_tokens, doc.completion_tokens)
        c = st.columns(5)
        c[0].metric("Pages parsed", f"{doc.pages}/{doc.total_pages}")
        c[1].metric("Chars", f"{doc.chars:,}")
        c[2].metric("Time", f"{last['secs']:.1f}s")
        c[3].metric("Tokens", f"{doc.total_tokens:,}")
        c[4].metric("~Cost", f"${cost:.3f}" if cost is not None else "—")
        st.caption(
            f"model: {doc.model} · detail: {last.get('detail', '?')} · "
            f"routing: **{doc.text_pages} text** (free) / **{doc.vision_pages} vision** · "
            f"{doc.prompt_tokens:,} in / {doc.completion_tokens:,} out "
            f"· {(last['secs'] / max(doc.pages, 1)):.1f}s/page"
        )

        for i, md in enumerate(doc.page_markdown, start=1):
            st.divider()
            route = doc.routes[i - 1] if i - 1 < len(doc.routes) else "?"
            badge = "🆓 text layer" if route == "text" else "👁 vision"
            st.markdown(f"### Page {i}  ·  {badge}")
            left, right = st.columns(2)
            with left:
                if i - 1 < len(last["imgs"]):
                    st.image(last["imgs"][i - 1], width="stretch")
            with right:
                with st.expander("raw Markdown"):
                    st.code(md, language="markdown")
                render_markdown(md)

# ---- record a result --------------------------------------------------------
st.divider()
with st.expander("➕ Record a test result"):
    with st.form("add_result", clear_on_submit=True):
        scope = st.text_input("What did you test? (scope)")
        verdict = st.radio("Verdict", ["win", "fail", "partial"], horizontal=True)
        note = st.text_area("What happened?")
        pdf_name = st.text_input("PDF", value=(last.get("name") if last else ""))
        if st.form_submit_button("Save result") and scope.strip():
            add_result(pdf_name, scope.strip(), verdict, note.strip())
            st.success("Recorded.")
            st.rerun()

# ---- the resume: where it wins & fails --------------------------------------
st.divider()
st.subheader("📋 Test log — where it wins & fails")
entries = load_log()
groups = {v: [e for e in entries if e.get("verdict") == v] for v in ("win", "fail", "partial")}
m = st.columns(3)
m[0].metric("✅ Wins", len(groups["win"]))
m[1].metric("❌ Fails", len(groups["fail"]))
m[2].metric("⚠️ Partial", len(groups["partial"]))
for v in ("fail", "partial", "win"):  # fails first — most actionable
    if groups[v]:
        st.markdown(f"**{_VERDICT[v]} {v.capitalize()}**")
        for e in groups[v]:
            meta = " · ".join(x for x in (e.get("pdf"), e.get("date")) if x)
            st.markdown(
                f"- **{e.get('scope', '')}** — {e.get('note', '')}  \n"
                f"  <span style='color:#888;font-size:0.85em'>{meta}</span>",
                unsafe_allow_html=True,
            )
