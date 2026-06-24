"""Shared helpers for the Noema test lab (multipage Streamlit app).

Path setup, the shared test report, the "log this run" control, timing, parser-result
caching, Markdown+LaTeX rendering, and a "show the real code" helper — so every page
behaves and looks the same. No decorative emojis; colour via Streamlit's `:color[...]`.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

MYPDFS = ROOT / "myTestPDFs"
RESULTS = ROOT / "results"
PARSER_RUNS = RESULTS / "parser_runs"
CONTEXT_RUNS = RESULTS / "context_runs"
LOG = RESULTS / "test_log.json"

VERDICTS = ("win", "fail", "partial")
VERDICT_COLOR = {"win": "green", "fail": "red", "partial": "orange"}


def style() -> None:
    """A little CSS for a calmer, more professional look. Call once per page."""
    st.markdown(
        "<style>#MainMenu,footer{visibility:hidden}"
        ".block-container{padding-top:2.5rem;max-width:1200px}"
        "h1,h2,h3{letter-spacing:-0.01em}"
        "[data-testid='stMetricValue']{font-size:1.4rem}</style>",
        unsafe_allow_html=True,
    )


def io_banner(input_type: str, output_type: str) -> None:
    """A consistent 'Input <type> -> Output <type>' line for every step."""
    st.markdown(
        f"<div style='padding:.5rem .8rem;border:1px solid #e5e7eb;border-radius:.5rem;"
        f"background:#fafafa;display:inline-block;font-size:.9rem'>"
        f"<b>Input</b> <code>{input_type}</code> &nbsp;→&nbsp; "
        f"<b>Output</b> <code>{output_type}</code></div>",
        unsafe_allow_html=True,
    )


@contextmanager
def timer():
    h = {}
    t0 = time.perf_counter()
    try:
        yield h
    finally:
        h["secs"] = time.perf_counter() - t0


# ---- the shared test report -------------------------------------------------
def load_log() -> list[dict]:
    if LOG.exists():
        try:
            return json.loads(LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def add_result(entry: dict) -> None:
    entries = load_log()
    entries.insert(0, {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), **entry})
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def save_run_button(tool: str, *, scope: str, inputs: dict, outputs: dict, key: str) -> None:
    """One-click logging of the current input -> output into the shared report."""
    st.markdown("**Log this run to the test report**")
    c = st.columns([1.4, 3, 1])
    verdict = c[0].radio("Verdict", VERDICTS, horizontal=True, key=f"{key}_v",
                         label_visibility="collapsed")
    note = c[1].text_input("Note", key=f"{key}_n", label_visibility="collapsed",
                           placeholder="what did you observe?")
    if c[2].button("Log run", key=f"{key}_b", width="stretch"):
        add_result({"tool": tool, "scope": scope, "verdict": verdict,
                    "note": note.strip(), "input": inputs, "output": outputs})
        st.success("Logged. See the Home page for the full report.")


# ---- parser result cache (so saved tests don't re-extract) ------------------
def parser_run_path(name: str) -> Path:
    return PARSER_RUNS / f"{Path(name).stem}.json"


def list_parser_runs() -> list[str]:
    if not PARSER_RUNS.exists():
        return []
    return sorted(p.name for p in PARSER_RUNS.glob("*.json"))


def load_parser_run(name: str) -> dict | None:
    p = parser_run_path(name)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_parser_run(name: str, record: dict) -> None:
    PARSER_RUNS.mkdir(parents=True, exist_ok=True)
    parser_run_path(name).write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                     encoding="utf-8")


def run_and_cache_parser(name, *, data=None, model=None, detail="high", scale=2.0,
                         max_pages=None, mode="auto") -> dict:
    from app.parsing import vision

    if data is None:
        data = (MYPDFS / name).read_bytes()
    with timer() as t:
        doc = vision.parse_pdf(data, name, model=model or None, detail=detail,
                               scale=scale, max_pages=max_pages, mode=mode)
    record = {
        "filename": doc.filename, "pages": doc.pages, "total_pages": doc.total_pages,
        "page_markdown": doc.page_markdown, "routes": doc.routes,
        "prompt_tokens": doc.prompt_tokens, "completion_tokens": doc.completion_tokens,
        "model": doc.model, "secs": round(t["secs"], 2), "detail": detail, "scale": scale,
        "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    save_parser_run(name, record)
    return record


# ---- contextual-retrieval result cache --------------------------------------
def context_run_path(name: str) -> Path:
    return CONTEXT_RUNS / f"{Path(name).stem}.json"


def list_context_runs() -> list[str]:
    if not CONTEXT_RUNS.exists():
        return []
    return sorted(p.name for p in CONTEXT_RUNS.glob("*.json"))


def load_context_run(name: str) -> dict | None:
    p = context_run_path(name)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_context_run(name: str, record: dict) -> None:
    CONTEXT_RUNS.mkdir(parents=True, exist_ok=True)
    context_run_path(name).write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                      encoding="utf-8")


def run_and_cache_context(name, markdown, *, model=None, target_tokens=512,
                          overlap_tokens=64) -> dict:
    from app.chunking import chunk_markdown
    from app.retrieval import contextualize_chunks

    chunks = chunk_markdown(markdown, doc_id=name, target_tokens=target_tokens,
                            overlap_tokens=overlap_tokens)
    with timer() as t:
        ctx = contextualize_chunks(markdown, chunks, model=model)
    record = {
        "name": name, "markdown": markdown, "model": model or "(default chat model)",
        "secs": round(t["secs"], 2),
        "prompt_tokens": sum(c.prompt_tokens for c in ctx),
        "completion_tokens": sum(c.completion_tokens for c in ctx),
        "cached_tokens": sum(c.cached_tokens for c in ctx),
        "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "items": [{
            "index": c.chunk.index, "section": c.chunk.section, "pages": c.chunk.pages,
            "chunk_text": c.chunk.text, "context": c.context, "contextual_text": c.text,
            "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens,
        } for c in ctx],
    }
    save_context_run(name, record)
    return record


# ---- rendering --------------------------------------------------------------
def page_images(data: bytes, *, scale: float = 1.6, max_pages=None):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    n = len(pdf) if max_pages is None else min(len(pdf), max_pages)
    return [pdf[i].render(scale=scale).to_pil() for i in range(n)]


def route_badge(route: str) -> str:
    return ":green[text layer]" if route == "text" else ":blue[vision]"


def verdict_badge(v: str) -> str:
    return f":{VERDICT_COLOR.get(v, 'gray')}[{v}]"


_FIGURE_TAG = re.compile(
    r"\*?\[\s*(Figure|Diagram|Chart|Image|Photo|Graph|Illustration)\b[^\]]*\]\*?", re.I)


def _normalize_math(md: str) -> str:
    md = re.sub(r"\\\((.+?)\\\)", r"$\1$", md, flags=re.S)
    md = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", md, flags=re.S)
    return md


def _render_text_with_figures(text: str) -> None:
    """Render text+LaTeX, but lift figure/diagram descriptions into a visible callout
    box — so the parser's '[Figure: …]' is obviously a *detected figure*, not body text."""
    pos = 0
    for m in _FIGURE_TAG.finditer(text):
        before = text[pos:m.start()]
        if before.strip():
            st.markdown(before)
        kind = m.group(1).upper()
        inside = m.group(0).strip().strip("*").strip()
        if inside.startswith("[") and inside.endswith("]"):
            inside = inside[1:-1].strip()
        st.markdown(
            f"<div style='border-left:3px solid #94a3b8;background:#f8fafc;color:#475569;"
            f"padding:.5rem .8rem;margin:.35rem 0;border-radius:.25rem'>"
            f"<span style='font-size:.72rem;letter-spacing:.06em;color:#64748b'>{kind} DETECTED</span>"
            f"<br>{inside}</div>",
            unsafe_allow_html=True,
        )
        pos = m.end()
    rest = text[pos:]
    if rest.strip():
        st.markdown(rest)


def render_markdown(md: str) -> None:
    md = _normalize_math(md)
    for part in re.split(r"(<table[\s\S]*?</table>)", md, flags=re.I):
        if not part.strip():
            continue
        if part.lstrip().lower().startswith("<table"):
            st.markdown(part, unsafe_allow_html=True)
        else:
            _render_text_with_figures(part)


def show_source(*objects, label: str = "Show the actual code") -> None:
    """Drop the real source of the given functions into an expander — so 'how it works'
    is the code itself, not a paraphrase."""
    with st.expander(label):
        for obj in objects:
            try:
                st.code(inspect.getsource(obj), language="python")
            except Exception:
                st.caption(f"(source unavailable for {getattr(obj, '__name__', obj)})")
