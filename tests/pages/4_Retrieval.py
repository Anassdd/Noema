"""Retrieval — build a RAG base, then watch a question flow through every stage to a
context list, and (optionally) a grounded cited answer.

Tabs: How it works (diagram + real code), Build the base (seed/ingest/reset),
Ask (type a question → dense → BM25 → fuse → rerank → context list → answer).
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from lab_common import (ROOT, io_banner, list_parser_runs, load_parser_run, page_images,
                        render_markdown, save_run_button, show_source, style, timer)
from app.chunking.base import Chunk  # noqa: E402
from app.config import settings  # noqa: E402
from app.parsing.base import ParsedDoc  # noqa: E402
from app.retrieval import (VectorStore, answer_from, ingest_markdown, ingest_parsed_doc,  # noqa: E402
                           search_trace)
from app.retrieval import rerank as _rerank  # noqa: E402
from app.retrieval.contextual import ContextualChunk  # noqa: E402

MYPDFS = ROOT / "myTestPDFs"

RAG_STORE = str(ROOT / "results" / "rag_store")
CTX_RUNS = ROOT / "results" / "context_runs"

st.set_page_config(page_title="Noema Lab — Retrieval", layout="wide")
style()
st.title("Retrieval")
st.caption(f"provider: {settings.provider} · embed model: {settings.embed_model} · "
           "hybrid dense + BM25, RRF fusion, optional rerank — over the contextualized chunks")
io_banner("question (str)", "ranked context (list[ScoredChunk]) → grounded Answer")

FLOW_DOT = """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box style="rounded,filled" fillcolor="#f3f4f6" fontname="Helvetica" fontsize=10];
  edge [fontname="Helvetica" fontsize=9 color="#999"];
  q [label="question"];
  emb [label="embed query"];
  d [label="DENSE search\\n(vector store)" fillcolor="#eff6ff"];
  b [label="BM25 search\\n(keyword, local)" fillcolor="#fef9c3"];
  f [label="fuse (RRF)"];
  r [label="rerank\\n(optional)"];
  c [label="top-k CONTEXT" fillcolor="#ecfdf5"];
  a [label="grounded answer\\n+ citations" fillcolor="#ecfdf5"];
  q -> emb -> d; q -> b; d -> f; b -> f; f -> r -> c -> a;
}
"""


def get_store():
    return VectorStore("default", path=RAG_STORE)


def parsed_doc_from_cache(name) -> ParsedDoc:
    """Rebuild a ParsedDoc from a cached parser run so we can ingest a PDF without re-parsing."""
    rec = load_parser_run(name)
    pm = rec["page_markdown"]
    return ParsedDoc(filename=rec["filename"], pages=rec["pages"], total_pages=rec["total_pages"],
                     page_markdown=pm, markdown="\n\n".join(pm), model=rec.get("model", ""),
                     routes=rec.get("routes", []))


def seed_from_context_runs(store) -> int:
    total = 0
    for fp in sorted(CTX_RUNS.glob("*.json")):
        rec = json.loads(fp.read_text(encoding="utf-8"))
        ccs = []
        for it in rec["items"]:
            sec = it.get("section", "") or ""
            ch = Chunk(chunk_id=f"{rec['name']}::{it['index']}", doc_id=rec["name"],
                       index=it["index"], text=it["chunk_text"],
                       header_path=sec.split(" › ") if sec else [], pages=it.get("pages") or [])
            ccs.append(ContextualChunk(chunk=ch, context=it.get("context", "")))
        total += store.add(ccs)
    return total


def show_hits(chunks, limit=None):
    for rank, c in enumerate(chunks[:limit] if limit else chunks, 1):
        sc = " · ".join(f"{k}={v}" for k, v in c.scores.items()) or "—"
        pages = ",".join(map(str, c.pages)) or "—"
        st.markdown(f"**{rank}.** `{c.chunk_id}` — {c.section or '_(no section)_'} · p.{pages}  \n"
                    f"<span style='color:#888;font-size:.82em'>{sc}</span>", unsafe_allow_html=True)
        st.caption((c.text[:220] + "…") if len(c.text) > 220 else c.text)


tab_how, tab_build, tab_docs, tab_ask = st.tabs(
    ["How it works", "Build the base", "Documents", "Ask"])

# ---- How it works -----------------------------------------------------------
with tab_how:
    st.subheader("Hybrid retrieval, step by step")
    st.graphviz_chart(FLOW_DOT, width="stretch")
    st.markdown(
        "1. **Embed the question** with the same model the chunks used.\n"
        "2. **Dense search** — nearest chunks by vector similarity (meaning).\n"
        "3. **BM25 search** — chunks sharing the exact query words (local, free).\n"
        "4. **Fuse (RRF)** — merge both ranked lists; a chunk found by *both* rises.\n"
        "5. **Rerank** (optional) — an LLM (or a hosted cross-encoder) reorders the top "
        "candidates by true relevance.\n"
        "6. **Context list** — the top-k chunks (original text + provenance) handed to the LLM.\n"
        "7. **Grounded answer** — generated from those sources only, with `[S#]` citations."
    )
    st.caption(f"Reranker: dedicated endpoint {'configured' if _rerank.endpoint_configured() else 'not configured'} "
               "— the lab's 'llm' mode works through the chat endpoint with no extra service.")
    show_source(search_trace, label="Show the actual search code")

# ---- Build the base ---------------------------------------------------------
with tab_build:
    store = get_store()
    recs = store.all_records()
    docs = sorted({r.doc_id for r in recs})
    c = st.columns(3)
    c[0].metric("Chunks in base", store.count())
    c[1].metric("Documents", len(docs))
    c[2].metric("Store", "Chroma (on-disk)")
    if docs:
        st.caption("Documents: " + " · ".join(docs))

    st.divider()
    st.markdown("**Ingest PDFs** — chunk → contextualize → embed → store (then ask about them)")
    pc = st.columns(2)
    with pc[0]:
        stems = [Path(r).stem for r in list_parser_runs()]
        picks = st.multiselect("Parsed example PDFs (already parsed — cheap: no vision call)", stems)
        if st.button("Ingest selected", disabled=not picks, width="stretch"):
            with st.spinner("chunk → contextualize → embed…"):
                for stem in picks:
                    ingest_parsed_doc(parsed_doc_from_cache(stem), domain_id="lab", store=store)
            st.success(f"Ingested {len(picks)} PDF(s). Base now has {store.count()} chunks.")
            st.rerun()
    with pc[1]:
        up = st.file_uploader("Upload a PDF (full parse — costs vision calls)", type="pdf")
        mp = st.number_input("Pages to parse (0 = all)", 0, value=2, step=1)
        if st.button("Parse + ingest", disabled=up is None, width="stretch"):
            from app.parsing import vision
            data = up.getvalue()
            MYPDFS.mkdir(exist_ok=True)
            (MYPDFS / up.name).write_bytes(data)  # keep so it can be read as-is later
            with st.spinner(f"parsing with {settings.parse_model} → chunk → contextualize → embed…"):
                doc = vision.parse_pdf(data, up.name, max_pages=None if mp == 0 else int(mp))
                ingest_parsed_doc(doc, domain_id="lab", store=store)
            st.success(f"Ingested '{up.name}'. Base now has {store.count()} chunks.")
            st.rerun()

    st.divider()
    cc = st.columns(2)
    with cc[0]:
        st.markdown("**Seed from the contextualized examples** (embeds them once)")
        if st.button("Seed / refresh from examples", width="stretch"):
            with st.spinner("embedding contextualized chunks…"):
                n = seed_from_context_runs(store)
            st.success(f"Base now has {store.count()} chunks ({n} upserted).")
            st.rerun()
        if st.button("Reset base", width="stretch"):
            store.reset()
            st.warning("Base cleared.")
            st.rerun()
    with cc[1]:
        st.markdown("**Ingest a Markdown document** (chunk → contextualize → embed)")
        with st.form("ingest_md", clear_on_submit=True):
            doc_id = st.text_input("Document name")
            md = st.text_area("Markdown", height=140)
            if st.form_submit_button("Ingest") and doc_id.strip() and md.strip():
                with st.spinner(f"ingesting with {settings.chat_model} + {settings.embed_model}…"):
                    info = ingest_markdown(md, doc_id.strip(), domain_id="lab", store=store)
                st.success(f"Ingested {info['chunks']} chunks from '{doc_id}'.")
                st.rerun()

# ---- Documents --------------------------------------------------------------
with tab_docs:
    store = get_store()
    recs = store.all_records()
    if not recs:
        st.info("The base is empty — go to **Build the base** and ingest a PDF or seed it.")
    else:
        docs = sorted({r.doc_id for r in recs})
        pick = st.selectbox("Document", docs)
        doc_chunks = sorted([r for r in recs if r.doc_id == pick],
                            key=lambda c: int(c.chunk_id.rsplit("::", 1)[-1]) if "::" in c.chunk_id else 0)
        pdf_path = MYPDFS / pick
        has_pdf = pick.lower().endswith(".pdf") and pdf_path.exists()
        st.caption(f"{len(doc_chunks)} chunks indexed from this document.")
        view = st.radio("View", ["Original PDF", "Chunks"], horizontal=True,
                        index=0 if has_pdf else 1)

        if view == "Original PDF" and has_pdf:
            st.caption(f"Reading {pick} as-is (rendered locally — no model call).")
            try:
                for i, im in enumerate(page_images(pdf_path.read_bytes(), scale=1.7), 1):
                    st.markdown(f"**Page {i}**")
                    st.image(im, width="stretch")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not render the PDF: {exc}")
        else:
            if view == "Original PDF" and not has_pdf:
                st.info("No source PDF for this document (it wasn't ingested from a PDF) — "
                        "showing its chunks.")
            for c in doc_chunks:
                st.divider()
                pages = ",".join(map(str, c.pages)) or "—"
                st.markdown(f"**`{c.chunk_id}`** — {c.section or '_(no section)_'} · page {pages} "
                            f"· {len(c.text)} chars")
                if c.context:
                    st.caption("context blurb (embedded for retrieval, not cited):")
                    st.success(c.context)
                with st.expander("chunk text (what gets cited)"):
                    render_markdown(c.text)

# ---- Ask --------------------------------------------------------------------
with tab_ask:
    store = get_store()
    if store.count() == 0:
        st.info("The base is empty — go to **Build the base** and seed it first.")
    else:
        st.caption(f"{store.count()} chunks indexed. Ask a question about the indexed documents "
                   "(they're about Hölder inequalities and RAG, from the seeded examples).")
        q = st.text_input("Question", placeholder="e.g. What makes contextual retrieval cheap?")
        k = st.columns(4)
        top_k = k[0].slider("Context size (k)", 1, 10, 5)
        rmode = k[1].selectbox("Rerank", ["off", "llm"], help="llm = one LLM call reorders the top candidates")
        dense_k = k[2].slider("Dense pool", 5, 40, 20)
        bm25_k = k[3].slider("BM25 pool", 5, 40, 20)

        if st.button("Retrieve", type="primary", disabled=not q.strip()):
            with st.spinner("embedding query → dense + BM25 → fuse → rerank…"), timer() as t:
                tr = search_trace(q, k=top_k, dense_k=dense_k, bm25_k=bm25_k,
                                  rerank_mode=rmode, store=store)
            st.session_state["rag_trace"] = {"tr": tr, "secs": t["secs"], "q": q, "rmode": rmode}
            st.session_state.pop("rag_answer", None)

        state = st.session_state.get("rag_trace")
        if state and state["q"] == q:
            tr = state["tr"]
            tm = tr.timings
            st.caption(f"dense {tm.get('dense_ms','?')}ms · bm25 {tm.get('bm25_ms','?')}ms"
                       + (f" · rerank {tm.get('rerank_ms','?')}ms" if tr.reranked_applied else "")
                       + f" · total {state['secs']*1000:.0f}ms")

            with st.expander(f"Stage 1 — DENSE (meaning) · {len(tr.dense)} hits"):
                show_hits(tr.dense, limit=8)
            with st.expander(f"Stage 2 — BM25 (keywords) · {len(tr.bm25)} hits"):
                show_hits(tr.bm25, limit=8)
            with st.expander(f"Stage 3 — FUSED (RRF) · {len(tr.fused)} candidates", expanded=not tr.reranked_applied):
                show_hits(tr.fused, limit=8)
            if tr.reranked_applied:
                with st.expander(f"Stage 4 — RERANKED ({state['rmode']})", expanded=True):
                    show_hits(tr.reranked, limit=8)

            st.markdown(f"### Final context ({len(tr.final)} chunks → the LLM)")
            show_hits(tr.final)

            save_run_button("retrieval", scope=f"query: {q[:50]}",
                            inputs={"source": "query", "k": top_k, "rerank": rmode},
                            outputs={"final_top": tr.final[0].chunk_id if tr.final else None,
                                     "candidates": len(tr.fused)},
                            key="rag_save")

            st.divider()
            if st.button("Generate grounded answer", key="rag_answer_btn"):
                with st.spinner(f"answering with {settings.chat_model}…"):
                    st.session_state["rag_answer"] = answer_from(q, tr.final)
            ans = st.session_state.get("rag_answer")
            if ans:
                st.markdown("#### Answer")
                render_markdown(ans.text)
                st.caption("Sources: " + " · ".join(f"[S{i+1}] {c.citation}"
                                                     for i, c in enumerate(ans.sources)))
