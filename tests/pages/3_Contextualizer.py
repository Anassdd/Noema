"""Contextualizer — Anthropic Contextual Retrieval (the contextualization step).

Three tabs: How it works (diagram + the real prompt + code), Saved tests (cached
contextualized examples, browse free), Live run (contextualize live, with cost/timing).
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from lab_common import (ROOT, io_banner, list_context_runs, load_context_run,
                        render_markdown, run_and_cache_context, save_context_run,
                        save_run_button, show_source, style, timer)
from app.chunking import chunk_markdown  # noqa: E402
from app.config import settings  # noqa: E402
from app.retrieval import contextual, contextualize_chunks  # noqa: E402

EXAMPLES = ROOT / "results" / "chunk_examples.json"

st.set_page_config(page_title="Noema Lab — Contextualizer", layout="wide")
style()
st.title("Contextualizer")
st.caption("Anthropic Contextual Retrieval — prepend an LLM blurb that situates each chunk "
           "in its parent document, before embedding and BM25.")
io_banner("document Markdown (str) + list[Chunk]", "list[ContextualChunk]  (blurb + chunk)")

FLOW_DOT = """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box style="rounded,filled" fillcolor="#f3f4f6" fontname="Helvetica" fontsize=11];
  edge [fontname="Helvetica" fontsize=9 color="#999"];
  doc [label="whole document\\n(stable, cacheable prefix)"];
  chunk [label="one chunk"];
  llm [shape=ellipse fillcolor="#eff6ff" label="LLM\\n'situate this chunk'"];
  ctx [label="context blurb\\n1-2 sentences"];
  out [label="contextual chunk\\nblurb + chunk\\n-> embed + BM25" fillcolor="#ecfdf5"];
  doc -> llm; chunk -> llm; llm -> ctx -> out;
}
"""


def load_examples():
    try:
        return json.loads(EXAMPLES.read_text(encoding="utf-8"))
    except Exception:
        return []


def show_items(items):
    for it in items:
        st.divider()
        st.markdown(f"**Chunk {it['index']}** · section: {it.get('section') or '_(none)_'} "
                    f"· page(s): {it.get('pages') or '_n/a_'}")
        left, right = st.columns(2)
        with left:
            st.caption("Original chunk")
            txt = it["chunk_text"]
            st.markdown(f"> {txt[:400]}{'…' if len(txt) > 400 else ''}")
        with right:
            st.caption("Context the LLM added")
            st.success(it["context"] or "(empty)")
        with st.expander("Contextual payload — what gets embedded + BM25-indexed"):
            st.code(it.get("contextual_text") or f"{it['context']}\n\n{it['chunk_text']}",
                    language="markdown")


tab_how, tab_saved, tab_live = st.tabs(["How it works", "Saved tests", "Live run"])

# ---- How it works -----------------------------------------------------------
with tab_how:
    st.subheader("1 — The idea")
    st.graphviz_chart(FLOW_DOT, width="stretch")
    a, b = st.columns(2)
    with a:
        st.markdown(
            "A chunk pulled out of its document loses context — *which* method, *which* result? "
            "So for each chunk the LLM sees the **entire parent document** plus the chunk and "
            "writes a **1–2 sentence** situating blurb.\n\n"
            "- The blurb is **prepended** to the chunk; the combined text is what gets "
            "**embedded** and **BM25-indexed**. Provenance metadata is unchanged.\n"
            "- It answers in the **document's language** (a French doc → a French blurb).\n"
            "- Reported impact: **−49%** retrieval failures, **−67%** with a reranker."
        )
    with b:
        st.markdown("**The exact prompt** (document first — see caching below):")
        st.code(contextual.PROMPT_TEMPLATE, language="text")

    st.divider()
    st.subheader("2 — Why it's cheap: prompt caching")
    st.markdown(
        "This is the heart of the method. The document is **identical on every chunk call** and "
        "placed at the **start** of the prompt, so the provider's **automatic prompt-prefix "
        "cache** serves it:\n"
        "- OpenAI-compatible endpoints cache a prompt prefix once it exceeds **~1024 tokens**; a "
        "cache hit is billed at roughly **10%** of normal input and is faster. The cache stays "
        "warm for several minutes.\n"
        "- So a document is paid **full price once** (the first chunk), then **~10%** for every "
        "other chunk of that document. Contextualizing the chunks **back-to-back** keeps the "
        "cache warm.\n"
        "- Below the ~1024-token threshold there's **no caching** — which is exactly why small "
        "documents show 0 cached and large ones show most of the prefix cached."
    )
    long = load_context_run("Long paper - caching demo (normal).json")
    if long and long.get("prompt_tokens"):
        pt, ctk = long["prompt_tokens"], long.get("cached_tokens", 0)
        cc = st.columns(3)
        cc[0].metric("Prompt tokens", pt)
        cc[1].metric("Served from cache", ctk)
        cc[2].metric("Cache hit", f"{ctk / pt * 100:.0f}%")
        st.caption("Live proof from the seeded long-document example (Saved tests).")

    st.divider()
    st.subheader("3 — Where it can go wrong")
    st.markdown(
        "- **The model adds a lead-in** like *“Here is the context:”*, or wraps the answer in "
        "quotes/code fences — that noise would get embedded. **Auto-stripped** by `_clean_context` "
        "(covered by tests).\n"
        "- **Tiny chunks** (a one-line heading) get **generic** context — low value, but harmless.\n"
        "- **A document too long for the context window** can't be sent whole — situate against "
        "the chunk's **section** instead (a future option).\n"
        "- **Small documents** don't hit the cache, so each chunk pays full prompt cost — fine, "
        "because small documents are cheap anyway.\n"
        "- **Hallucinated context** (a blurb mentioning something not in the doc) is mitigated by "
        "`temperature=0` and *“situate within THIS document”* — and you can **verify it yourself** "
        "by reading the input document shown in Saved tests next to each blurb."
    )
    show_source(contextual.contextualize_chunk, contextual._clean_context,
                label="Show the actual code (call + the cleaning step)")

# ---- Saved tests ------------------------------------------------------------
with tab_saved:
    st.subheader("Cached examples")
    st.caption("Contextualized once and saved, so you can read them without paying for LLM "
               "calls. Add your own below (runs once, then it's cached here).")
    runs = list_context_runs()
    if runs:
        pick = st.selectbox("Example", runs)
        rec = load_context_run(pick)
        if rec:
            pt, ctk = rec.get("prompt_tokens", 0), rec.get("cached_tokens", 0)
            m = st.columns(5)
            m[0].metric("Chunks", len(rec["items"]))
            m[1].metric("Prompt tokens", pt)
            m[2].metric("Served from cache", ctk)
            m[3].metric("Completion", rec.get("completion_tokens", 0))
            m[4].metric("Time", f"{rec.get('secs', 0)}s")
            hit = f"{ctk / pt * 100:.0f}%" if pt else "n/a"
            st.caption(f"model: {rec.get('model')} · cached {rec.get('cached_at', '—')} · "
                       f"prompt cache hit: {hit} — no LLM call made now")
            with st.expander("Input document — read it to verify the blurbs", expanded=False):
                st.code(rec.get("markdown", ""), language="markdown")
                render_markdown(rec.get("markdown", "") or "_(empty)_")
            show_items(rec["items"])
    else:
        st.info("No cached examples yet. Add one below.")

    st.divider()
    st.markdown("**Add your own (paste a document, it gets chunked then contextualized)**")
    with st.form("add_context", clear_on_submit=False):
        cname = st.text_input("Name")
        cmd = st.text_area("Markdown document", height=180)
        submitted = st.form_submit_button("Contextualize and save")
    if submitted and cname.strip() and cmd.strip():
        with st.spinner(f"chunk + contextualize with {settings.chat_model} (one-time)…"):
            run_and_cache_context(cname.strip(), cmd)
        st.success(f"Saved. '{cname.strip()}' is in the Example list above.")
        st.rerun()

# ---- Live run ---------------------------------------------------------------
with tab_live:
    st.subheader("Contextualize live")
    st.warning("This calls the LLM once per chunk (a few cents). The document is the prompt "
               "prefix, so the per-chunk cost drops with prompt caching.")
    source = st.radio("Source", ["Example", "Paste Markdown"], horizontal=True)
    markdown, label = "", ""
    if source == "Example":
        ex = load_examples()
        if ex:
            pick = st.selectbox("Example", [e["name"] for e in ex], key="ctx_ex")
            markdown = next(e for e in ex if e["name"] == pick)["markdown"]
            label = pick
    else:
        markdown = st.text_area("Markdown document", height=180,
                                value="# Title\n\nIntro paragraph.\n\n## Method\n\nWe do X.")
        label = "pasted"

    chunks_preview = chunk_markdown(markdown, doc_id=label or "doc")
    st.caption(f"{len(chunks_preview)} chunk(s) → {len(chunks_preview)} LLM call(s)")

    if st.button("Run contextualization", type="primary", disabled=not markdown.strip()):
        with st.spinner(f"contextualizing with {settings.chat_model}…"), timer() as t:
            ctx = contextualize_chunks(markdown, chunks_preview)
        st.session_state["ctx_live"] = {
            "label": label, "secs": t["secs"], "markdown": markdown,
            "p_tok": sum(c.prompt_tokens for c in ctx),
            "c_tok": sum(c.completion_tokens for c in ctx),
            "cache_tok": sum(c.cached_tokens for c in ctx),
            "items": [{"index": c.chunk.index, "section": c.chunk.section, "pages": c.chunk.pages,
                       "chunk_text": c.chunk.text, "context": c.context,
                       "contextual_text": c.text} for c in ctx],
        }

    live = st.session_state.get("ctx_live")
    if live and live["label"] == label:
        pt, ctk = live["p_tok"], live.get("cache_tok", 0)
        m = st.columns(5)
        m[0].metric("Chunks", len(live["items"]))
        m[1].metric("Prompt tokens", pt)
        m[2].metric("From cache", ctk)
        m[3].metric("Completion", live["c_tok"])
        m[4].metric("Time", f"{live['secs']:.1f}s")
        st.caption(f"prompt cache hit: {ctk / pt * 100:.0f}% — caching needs a >1024-token "
                   "document prefix, so small docs show 0." if pt else "")
        save_run_button("contextualizer", scope=f"contextualize {label}",
                        inputs={"source": label, "chunks": len(live["items"])},
                        outputs={"prompt_tokens": pt, "cached_tokens": ctk,
                                 "completion_tokens": live["c_tok"], "secs": round(live["secs"], 1)},
                        key="ctx_save")
        with st.expander("Input document — read it to verify the blurbs"):
            render_markdown(live["markdown"] or "_(empty)_")
        show_items(live["items"])
