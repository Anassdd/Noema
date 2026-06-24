"""Chunker — Markdown to provenance-tagged chunks.

Three tabs: How it works (diagram + real code), Saved tests (use cases + edge cases
with the input visible), Live run (watch blocks -> sections -> chunks execute, timed).
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from lab_common import (ROOT, io_banner, render_markdown, save_run_button, show_source,
                        style, timer, verdict_badge)
from app.chunking import chunk_markdown, chunk_parsed_doc  # noqa: E402
import app.chunking.markdown_chunker as mc  # noqa: E402
from app.chunking.tokens import count_tokens  # noqa: E402
from app.config import settings  # noqa: E402

EXAMPLES = ROOT / "results" / "chunk_examples.json"
MYPDFS = ROOT / "myTestPDFs"

st.set_page_config(page_title="Noema Lab — Chunker", layout="wide")
style()
st.title("Chunker")
st.caption("Structure-aware recursive Markdown chunking — the SOTA default. No model call, "
           "no GPU, deterministic.")
io_banner("Markdown (str) — or a ParsedDoc for page provenance", "list[Chunk]  (text + provenance)")

STAGES_DOT = """
digraph G {
  rankdir=LR; bgcolor="transparent";
  node [shape=box style="rounded,filled" fillcolor="#f3f4f6" fontname="Helvetica" fontsize=10];
  edge [fontname="Helvetica" fontsize=9 color="#999"];
  md [label="Markdown (str)\\nor ParsedDoc"];
  blocks [label="1. blocks\\nheading | paragraph |\\ncode | $$math$$ | table\\n(each keeps a char span)"];
  sections [label="2. sections\\ngrouped under\\ntheir heading path"];
  pack [label="3. pack\\nfill up to target tokens;\\nsplit an oversized block\\npara - sentence - chars"];
  overlap [label="4. overlap\\ncarry the tail of the\\nprevious chunk (same section)"];
  chunks [label="list[Chunk]\\ntext + {doc, page(s),\\nsection, tokens}" fillcolor="#ecfdf5"];
  md -> blocks -> sections -> pack -> overlap -> chunks;
}
"""

STRUCTURE_DOT = """
digraph G {
  rankdir=TB; bgcolor="transparent"; ranksep=0.45;
  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10];
  edge [color="#bbb"];
  doc  [label="document: paper.pdf" fillcolor="#eef2ff"];
  h1   [label="# Hölder Inequalities" fillcolor="#f3f4f6"];
  meth [label="## Methods" fillcolor="#f3f4f6"];
  data [label="### Data" fillcolor="#f3f4f6"];
  res  [label="## Results" fillcolor="#f3f4f6"];
  k0 [shape=note label="Chunk 0\\nsection: Hölder Inequalities\\npage 1" fillcolor="#ecfdf5"];
  k1 [shape=note label="Chunk 1\\nsection: …Methods\\npage 1" fillcolor="#ecfdf5"];
  k2 [shape=note label="Chunk 2\\nsection: …Methods.Data\\npage 1" fillcolor="#ecfdf5"];
  k3 [shape=note label="Chunk 3\\nsection: …Results\\npage 2" fillcolor="#ecfdf5"];
  doc -> h1; h1 -> meth; meth -> data; h1 -> res;
  h1 -> k0; meth -> k1; data -> k2; res -> k3;
}
"""


def load_examples():
    try:
        return json.loads(EXAMPLES.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_examples(items):
    EXAMPLES.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def block_kind(b):
    if b.kind == "heading":
        return f"heading H{b.level}"
    t = b.text.lstrip()
    if t.startswith(("```", "~~~")):
        return "code"
    if t.startswith("$$"):
        return "math"
    if t.lower().startswith("<table"):
        return "html-table"
    if "|" in (t.splitlines() or [""])[0]:
        return "table"
    return "paragraph"


def show_chunks(chunks):
    for ch in chunks:
        st.divider()
        head = f"**Chunk {ch.index}** · {ch.token_count} tok"
        if ch.overlap_tokens:
            head += f" · {ch.overlap_tokens} overlap"
        st.markdown(head)
        meta = st.columns(3)
        meta[0].markdown(f"section: {ch.section or '_(none)_'}")
        meta[1].markdown(f"page(s): {ch.pages or '_n/a_'}")
        meta[2].markdown(f"`{ch.chunk_id}`")
        with st.expander("raw text"):
            st.code(ch.text, language="markdown")
        render_markdown(ch.text)


tab_how, tab_saved, tab_live = st.tabs(["How it works", "Saved tests", "Live run"])

# ---- How it works -----------------------------------------------------------
with tab_how:
    st.subheader("1 — The pipeline")
    st.graphviz_chart(STAGES_DOT, width="stretch")
    st.markdown(
        "The chunker is deliberately simple, because research shows **the cut is "
        "low-leverage** — recursive structure-aware splitting at ~512 tokens is the SOTA, and "
        "fancier *semantic* splitting is slower without being consistently better. The care goes "
        "into **structure** and **provenance**, not boundary cleverness.\n\n"
        "**1 · Split into blocks.** The Markdown is scanned line by line into typed blocks — "
        "headings, paragraphs, lists, fenced code, `$$…$$` display math, and tables. Each block "
        "remembers its **character span**, which is later mapped back to page numbers.\n\n"
        "**2 · Group into sections.** Blocks are grouped under the **heading path** above them "
        "(`Methods › Data`). Content before any heading sits under the empty path.\n\n"
        "**3 · Pack to target.** Within a section, blocks are packed greedily until adding the "
        "next would exceed **`target_tokens`**. A single block bigger than the target is split "
        "**recursively** — paragraphs → sentences → hard character windows — and **atomic blocks "
        "(code, `$$…$$`, tables) are never split**. LaTeX stays inline as text.\n\n"
        "**4 · Overlap.** The tail (~`overlap_tokens`) of the previous chunk is prepended to the "
        "next one *within the same section*, so a sentence or entity sitting on a boundary "
        "survives in at least one chunk — important for the later graph step. No overlap across "
        "section boundaries (different topics)."
    )

    st.divider()
    st.subheader("2 — How the structure is represented")
    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.graphviz_chart(STRUCTURE_DOT, width="stretch")
    with c2:
        st.markdown(
            "Chunks **mirror the document's heading hierarchy**. Each chunk is a leaf that "
            "remembers the **full heading path** it came from and the **page(s)** it spans — "
            "so a chunk is never an anonymous slice of text; it always knows *where in the "
            "document it lives*.\n\n"
            "- The **section** (`A › B › C`) is the breadcrumb used for context and filtering.\n"
            "- The **page(s)** come for free from the parser's per-page Markdown; a chunk that "
            "straddles a page break carries **both** pages.\n"
            "- This is exactly what grounded citation needs: *doc + page + section*."
        )

    st.divider()
    st.subheader("3 — The output: a Chunk")
    st.markdown(
        "Each chunk is a small record. The text is what gets embedded; the rest is provenance "
        "and bookkeeping:"
    )
    st.markdown(
        "| field | type | meaning |\n| --- | --- | --- |\n"
        "| `chunk_id` | str | `doc::index`, stable id |\n"
        "| `text` | str | the passage (incl. any overlap prefix) |\n"
        "| `header_path` | list[str] | `['Methods','Data']` → `section` = `Methods › Data` |\n"
        "| `pages` | list[int] | source page(s) — provenance |\n"
        "| `token_count` / `char_count` | int | size |\n"
        "| `overlap_tokens` | int | leading tokens carried from the previous chunk |\n"
        "| `domain_id` | str | `default` for now (multi-domain later) |"
    )
    demo = chunk_markdown(
        "# Title\n\n## Section A\n\nA paragraph of prose that is long enough to stand as its own "
        "chunk so the example shows real field values.",
        doc_id="example.md")[-1].to_dict()
    st.caption("A live example chunk (from chunking a tiny document):")
    st.json(demo)

    st.divider()
    cols = st.columns([1, 1])
    with cols[0]:
        st.markdown("**Defaults (from the code):**")
        st.json({"target_tokens": 512, "overlap_tokens": 64, "min_tokens": 64,
                 "tokenizer": "tiktoken o200k_base if installed, else ~4 chars/token"})
    with cols[1]:
        st.caption("`min_tokens`: a trailing chunk smaller than this merges into the previous "
                   "one, so you don't get a stray two-word chunk at the end of a section.")
    show_source(mc.chunk_markdown, mc._pack, mc._blocks, label="Show the actual chunker code")

# ---- Saved tests ------------------------------------------------------------
with tab_saved:
    st.subheader("Use cases and edge cases")
    st.caption("Seeded examples, chunked live (chunking is free). Input shown visually; "
               "add your own at the bottom.")
    examples = load_examples()
    summary = []
    for e in examples:
        ch = chunk_markdown(e["markdown"], doc_id=e["name"])
        toks = [c.token_count for c in ch]
        summary.append({"name": e["name"], "category": e["category"], "chunks": len(ch),
                        "sections": len({c.section for c in ch}),
                        "max_tok": max(toks) if toks else 0, "note": e.get("note", "")})
    st.dataframe(summary, width="stretch", hide_index=True)

    names = [e["name"] for e in examples]
    if names:
        pick = st.selectbox("Inspect an example", names)
        ex = next(e for e in examples if e["name"] == pick)
        st.markdown(f"_{ex['category']}_ — {ex.get('note', '')}")
        left, right = st.columns(2)
        with left:
            st.markdown("**Input (Markdown)**")
            with st.expander("raw", expanded=False):
                st.code(ex["markdown"], language="markdown")
            render_markdown(ex["markdown"] or "_(empty)_")
        with right:
            with timer() as t:
                ch = chunk_markdown(ex["markdown"], doc_id=ex["name"])
            st.markdown(f"**Output — {len(ch)} chunks in {t['secs'] * 1000:.1f} ms**")
            show_chunks(ch)

    st.divider()
    with st.expander("Add an example to the library"):
        with st.form("add_example", clear_on_submit=True):
            ename = st.text_input("Name")
            ecat = st.radio("Category", ["normal", "edge"], horizontal=True)
            enote = st.text_input("Note (what it tests)")
            emd = st.text_area("Markdown", height=180)
            if st.form_submit_button("Save example") and ename.strip() and emd.strip():
                items = load_examples()
                items.append({"name": ename.strip(), "category": ecat,
                              "note": enote.strip(), "markdown": emd})
                save_examples(items)
                st.success("Saved.")
                st.rerun()

# ---- Live run ---------------------------------------------------------------
with tab_live:
    st.subheader("Watch the stages execute")
    source = st.radio("Source", ["Paste Markdown", "Example", "Upload PDF"], horizontal=True)
    markdown, parsed_doc, label = "", None, ""

    if source == "Paste Markdown":
        markdown = st.text_area("Markdown", height=200,
                                value="# Title\n\nParagraph one.\n\n## Section\n\nParagraph two.")
        label = "pasted"
    elif source == "Example":
        ex = load_examples()
        if ex:
            pick = st.selectbox("Example", [e["name"] for e in ex], key="live_ex")
            markdown = next(e for e in ex if e["name"] == pick)["markdown"]
            label = pick
    else:
        up = st.file_uploader("PDF (parses then chunks)", type="pdf")
        if up:
            mp = st.number_input("Pages (0=all)", 0, value=2, step=1)
            if st.button("Parse PDF"):
                from app.parsing import vision
                with st.spinner(f"parsing with {settings.parse_model}…"):
                    parsed_doc = vision.parse_pdf(up.getvalue(), up.name,
                                                  max_pages=None if mp == 0 else int(mp))
                st.session_state["chunk_doc"] = parsed_doc
            parsed_doc = st.session_state.get("chunk_doc")
            label = getattr(parsed_doc, "filename", "")

    c = st.columns(3)
    target = c[0].slider("Target tokens", 64, 1024, 512, 32)
    overlap = c[1].slider("Overlap tokens", 0, 256, 64, 16)
    min_tok = c[2].slider("Min tokens", 0, 256, 64, 16)

    if st.button("Chunk", type="primary", disabled=not (markdown.strip() or parsed_doc)):
        text = parsed_doc.markdown if parsed_doc is not None else markdown
        blocks = mc._blocks(text or "")
        sections = mc._sections(blocks)
        with timer() as t:
            if parsed_doc is not None:
                chunks = chunk_parsed_doc(parsed_doc, target_tokens=target,
                                          overlap_tokens=overlap, min_tokens=min_tok)
            else:
                chunks = chunk_markdown(markdown, doc_id=label or "pasted", target_tokens=target,
                                        overlap_tokens=overlap, min_tokens=min_tok)
        st.session_state["chunk_trace"] = {
            "blocks": [(block_kind(b), count_tokens(b.text), b.text[:80]) for b in blocks],
            "sections": [(" › ".join(p) or "(none)", len(bs)) for p, bs in sections],
            "chunks": chunks, "secs": t["secs"], "label": label,
            "knobs": {"target": target, "overlap": overlap, "min": min_tok},
        }

    tr = st.session_state.get("chunk_trace")
    if tr:
        m = st.columns(4)
        toks = [c.token_count for c in tr["chunks"]]
        m[0].metric("Chunks", len(tr["chunks"]))
        m[1].metric("Avg tok", f"{sum(toks) // len(toks)}" if toks else 0)
        m[2].metric("Max tok", max(toks) if toks else 0)
        m[3].metric("Time", f"{tr['secs'] * 1000:.1f} ms")

        if tr["chunks"]:
            save_run_button("chunker", scope=f"chunk {tr['label']}",
                            inputs={"source": tr["label"], **tr["knobs"]},
                            outputs={"chunks": len(tr["chunks"]), "max_tok": max(toks),
                                     "sections": len({c.section for c in tr["chunks"]})},
                            key="live_chunk_save")

        with st.expander(f"Stage 1 — blocks ({len(tr['blocks'])})"):
            st.dataframe([{"kind": k, "tokens": n, "preview": p} for k, n, p in tr["blocks"]],
                         width="stretch", hide_index=True)
        with st.expander(f"Stage 2 — sections ({len(tr['sections'])})"):
            st.dataframe([{"section": s, "blocks": n} for s, n in tr["sections"]],
                         width="stretch", hide_index=True)
        st.markdown(f"**Stage 3 — {len(tr['chunks'])} chunks**")
        show_chunks(tr["chunks"])
