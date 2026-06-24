"""Parser — vision PDF parser testbench.

Three tabs: How it works (diagram + real code), Saved tests (cached results, browse
without re-extracting, add your own), Live run (watch the routing decision execute).
"""

from __future__ import annotations

import streamlit as st

from lab_common import (MYPDFS, io_banner, list_parser_runs, load_parser_run, page_images,
                        render_markdown, route_badge, run_and_cache_parser,
                        save_run_button, style, timer)
from app.config import settings  # noqa: E402
from app.parsing import vision  # noqa: E402

st.set_page_config(page_title="Noema Lab — Parser", layout="wide")
style()
st.title("Parser")
st.caption(f"provider: {settings.provider} · default parse model: {settings.parse_model} "
           "· pages render locally; only hard pages call the vision model")
io_banner("PDF file (bytes)", "Markdown + LaTeX per page  (ParsedDoc)")

ROUTING_DOT = """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box style="rounded,filled" fillcolor="#f3f4f6" fontname="Helvetica" fontsize=11];
  edge [fontname="Helvetica" fontsize=9 color="#999"];
  page [label="PDF page"];
  text [label="read embedded\\ntext layer (free, local)"];
  dec  [shape=diamond fillcolor="#fff7ed"
        label="clean prose?\\n>=200 chars, >=0.85 legible, no math\\nAND no figure?"];
  troute [label="TEXT route\\n0 tokens, instant" fillcolor="#ecfdf5"];
  vroute [label="VISION route\\nrender -> vision model\\n-> Markdown + LaTeX" fillcolor="#eff6ff"];
  page -> text -> dec;
  dec -> troute [label="yes"];
  dec -> vroute [label="no"];
}
"""


def routing_rows(data, max_pages=None):
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    n = len(pdf) if max_pages is None else min(len(pdf), max_pages)
    rows = []
    for i in range(n):
        page = pdf[i]
        text = vision._page_text(page)
        rows.append({
            "page": i + 1,
            "chars": len(text.strip()),
            "legibility": round(vision._legibility(text), 2),
            "has_math": bool(vision._MATH.search(text)),
            "has_figure": vision._has_figure(page),
            "route": "text" if vision._route_to_text(page, text) else "vision",
        })
    return rows


def show_result(record: dict, data: bytes):
    cols = st.columns(5)
    routes = record.get("routes", [])
    cols[0].metric("Pages", f"{record['pages']}/{record['total_pages']}")
    cols[1].metric("Text / Vision", f"{routes.count('text')} / {routes.count('vision')}")
    cols[2].metric("Tokens", record.get("prompt_tokens", 0) + record.get("completion_tokens", 0))
    cols[3].metric("Parse time", f"{record.get('secs', 0)}s")
    cols[4].metric("Cached", record.get("cached_at", "—"))
    st.caption(f"model: {record.get('model')} · detail: {record.get('detail')} "
               f"· no model call made now — showing the saved result")
    try:
        imgs = page_images(data, scale=1.5, max_pages=record["pages"])
    except Exception:
        imgs = []
    for i, md in enumerate(record["page_markdown"]):
        st.divider()
        route = routes[i] if i < len(routes) else "?"
        st.markdown(f"**Page {i + 1}** — {route_badge(route)}")
        left, right = st.columns(2)
        with left:
            if i < len(imgs):
                st.image(imgs[i], width="stretch")
        with right:
            with st.expander("raw Markdown"):
                st.code(md, language="markdown")
            render_markdown(md)


tab_how, tab_saved, tab_live = st.tabs(["How it works", "Saved tests", "Live run"])

# ---- How it works -----------------------------------------------------------
with tab_how:
    st.subheader("Per-page tiered routing")
    st.graphviz_chart(ROUTING_DOT, width="stretch")
    a, b = st.columns(2)
    with a:
        st.markdown(
            "Every page takes the **cheapest safe path**:\n"
            "- **Text layer (free)** when the page is confidently clean prose with no figure.\n"
            "- **Vision** otherwise — garbled/scanned/broken-font, any math, tables, or a figure.\n\n"
            "A page with a long paragraph *and* a diagram still goes to vision, so the figure "
            "is never silently dropped."
        )
    with b:
        st.markdown("**Live thresholds (read from the code):**")
        st.json({
            "min_chars": vision._MIN_TEXT,
            "min_legibility": vision._MIN_LEGIBILITY,
            "figure: min image area": vision._MIN_IMG_AREA,
            "figure: max prose paths": vision._MAX_PROSE_PATHS,
        })
    from lab_common import show_source
    show_source(vision._route_to_text, vision._is_clean_prose, vision._has_figure,
                label="Show the actual routing code")

# ---- Saved tests ------------------------------------------------------------
with tab_saved:
    st.subheader("Saved results")
    st.caption("Browse the parsed output of example PDFs without paying for a new model "
               "call. Add your own PDF below — it runs once, then it's cached here too.")
    runs = list_parser_runs()
    if runs:
        pick = st.selectbox("Example", runs)
        rec = load_parser_run(pick)
        pdf_path = MYPDFS / rec["filename"] if rec else None
        if rec and pdf_path and pdf_path.exists():
            show_result(rec, pdf_path.read_bytes())
        elif rec:
            st.warning(f"Cached result found but the source PDF '{rec['filename']}' is missing "
                       f"from myTestPDFs/, so pages can't be rendered.")
    else:
        st.info("No cached results yet. Add a PDF below to create one.")

    st.divider()
    st.markdown("**Add your own test PDF**")
    up = st.file_uploader("PDF", type="pdf", key="saved_upload")
    c = st.columns(3)
    detail = c[0].selectbox("Vision detail", ["high", "auto", "low"], key="saved_detail")
    mp = c[1].number_input("Pages (0 = all)", 0, value=0, step=1, key="saved_pages")
    if c[2].button("Parse and save", type="primary", disabled=up is None, width="stretch"):
        data = up.getvalue()
        (MYPDFS).mkdir(exist_ok=True)
        (MYPDFS / up.name).write_bytes(data)  # keep the PDF so pages can be rendered later
        with st.spinner(f"parsing {up.name} with {settings.parse_model} (one-time)…"):
            run_and_cache_parser(up.name, data=data, detail=detail,
                                 max_pages=None if mp == 0 else int(mp))
        st.success(f"Saved. '{up.name}' is now in the Example list above.")
        st.rerun()

# ---- Live run ---------------------------------------------------------------
with tab_live:
    st.subheader("Watch the routing decide, live")
    st.caption("The decision below is computed from the FREE signals only (text layer, "
               "legibility, math, figure) — no model call. It is exactly what the parser runs.")
    src = st.radio("Source", ["myTestPDFs", "Upload"], horizontal=True, key="live_src")
    data, name = None, None
    if src == "myTestPDFs":
        pdfs = sorted(MYPDFS.glob("*.pdf"))
        if pdfs:
            choice = st.selectbox("File", [p.name for p in pdfs], key="live_pick")
            data, name = (MYPDFS / choice).read_bytes(), choice
    else:
        up2 = st.file_uploader("PDF", type="pdf", key="live_upload")
        if up2:
            data, name = up2.getvalue(), up2.name

    if data:
        with timer() as t:
            rows = routing_rows(data)
        st.dataframe(rows, width="stretch", hide_index=True)
        free = sum(r["route"] == "text" for r in rows)
        st.caption(f"decided {len(rows)} pages in {t['secs'] * 1000:.0f} ms "
                   f"· {free} free (text) / {len(rows) - free} vision · no tokens spent")

        st.markdown("**Run the actual parse** (calls the vision model on vision-routed pages):")
        if st.button("Run full parse", type="primary", key="live_run"):
            with st.spinner(f"parsing with {settings.parse_model}…"), timer() as pt:
                doc = vision.parse_pdf(data, name)
            st.session_state["live_doc"] = {"doc": doc, "secs": pt["secs"], "name": name}

        live = st.session_state.get("live_doc")
        if live and live["name"] == name:
            doc = live["doc"]
            m = st.columns(4)
            m[0].metric("Time", f"{live['secs']:.1f}s")
            m[1].metric("Pages", doc.pages)
            m[2].metric("Tokens", doc.total_tokens)
            m[3].metric("Time/page", f"{live['secs'] / max(doc.pages, 1):.1f}s")
            save_run_button("parser", scope=f"parse {name}",
                            inputs={"source": name, "detail": "high"},
                            outputs={"text_pages": doc.text_pages, "vision_pages": doc.vision_pages,
                                     "tokens": doc.total_tokens, "secs": round(live["secs"], 1)},
                            key="live_save")
            for i, md in enumerate(doc.page_markdown):
                st.divider()
                st.markdown(f"**Page {i + 1}** — {route_badge(doc.routes[i])}")
                render_markdown(md)
