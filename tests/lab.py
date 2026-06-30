"""Noema — a simple playground: add documents, ask questions, get cited answers.

Run:
    backend/.venv/bin/python -m streamlit run tests/lab.py

This is the easy front door — drop a PDF, ask a question, read the answer with its
sources. The detailed inspector pages (Parser, Chunker, Contextualizer, Retrieval) are
in the sidebar for when you want to see how each step works.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import streamlit as st

from lab_common import ROOT, load_log, render_markdown, verdict_badge
from app.config import settings  # noqa: E402
from app.parsing.base import ParsedDoc  # noqa: E402
from app.retrieval import (VectorStore, answer_from, ingest_parsed_doc,  # noqa: E402
                           search_trace)

DOMAIN = "default"
RAG_STORE = str(ROOT / "results" / "rag_store")
MYPDFS = ROOT / "myTestPDFs"
PARSER_RUNS = ROOT / "results" / "parser_runs"
SAMPLE = "resonance_of_sector_7"

st.set_page_config(page_title="Noema", page_icon="◆", layout="centered")

st.markdown("""
<style>
#MainMenu, footer {visibility:hidden}
.block-container {padding-top:2rem; max-width:820px}
.hero {text-align:center; margin:.4rem 0 1.4rem}
.hero h1 {font-size:2.7rem; font-weight:800; letter-spacing:-.04em; margin:0;
  background:linear-gradient(95deg,#2563eb,#7c3aed); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent}
.hero p {color:#6b7280; font-size:1.02rem; margin:.3rem 0 0}
.stChatMessage {border-radius:14px}
div[data-testid="stChatMessageContent"] {font-size:1.0rem; line-height:1.55}
.srcline {margin:.7rem 0 .35rem; font-size:.82rem; color:#6b7280}
.pill {display:inline-block; background:#eef2ff; color:#4338ca; border:1px solid #e0e7ff;
  border-radius:999px; padding:.08rem .55rem; margin:0 .3rem .3rem 0; font-size:.78rem;
  font-weight:600}
.src {border:1px solid #eceef2; border-left:3px solid #7c3aed; border-radius:10px;
  padding:.6rem .85rem; margin:.45rem 0; background:#fff}
.src-head {display:flex; align-items:center; gap:.5rem; margin-bottom:.1rem}
.badge {background:linear-gradient(95deg,#2563eb,#7c3aed); color:#fff; font-size:.72rem;
  font-weight:700; border-radius:6px; padding:.05rem .42rem}
.src-doc {font-weight:600; color:#111827; font-size:.9rem}
.src-page {color:#6b7280; font-size:.8rem; margin-left:auto; white-space:nowrap}
.src-sec {color:#9ca3af; font-size:.7rem; letter-spacing:.04em; text-transform:uppercase;
  margin:.1rem 0 .35rem}
.src-text {color:#4b5563; font-size:.88rem; line-height:1.5; font-style:italic}
.doc-row {display:flex; justify-content:space-between; padding:.35rem .1rem;
  border-bottom:1px solid #f1f1f4; font-size:.9rem}
.doc-row span:last-child {color:#9ca3af}
.stButton>button {border-radius:10px}
section[data-testid="stSidebar"] {background:#fcfcfd}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_store():
    return VectorStore(DOMAIN, path=RAG_STORE)


def list_docs(store):
    docs: dict[str, dict] = {}
    for r in store.all_records():
        d = docs.setdefault(r.doc_id, {"chunks": 0, "pages": set()})
        d["chunks"] += 1
        d["pages"].update(r.pages)
    return docs


def ingest_sample(store):
    rec = json.loads((PARSER_RUNS / f"{SAMPLE}.json").read_text(encoding="utf-8"))
    pm = rec["page_markdown"]
    doc = ParsedDoc(filename=rec["filename"], pages=rec["pages"],
                    total_pages=rec["total_pages"], page_markdown=pm,
                    markdown="\n\n".join(pm), model=rec.get("model", ""),
                    routes=rec.get("routes", []))
    ingest_parsed_doc(doc, domain_id=DOMAIN, store=store)


def ingest_upload(store, name, data, max_pages):
    from app.parsing import vision
    MYPDFS.mkdir(exist_ok=True)
    (MYPDFS / name).write_bytes(data)
    doc = vision.parse_pdf(data, name, max_pages=None if max_pages == 0 else int(max_pages))
    ingest_parsed_doc(doc, domain_id=DOMAIN, store=store)


def _pages_str(pages):
    return "p. " + "–".join(str(p) for p in pages) if pages else ""


_LEAD_HEADING = re.compile(r"^\s*#{1,6}\s+.*?(?:\n+|$)")


def _passage(text):
    """A clean one-paragraph preview: drop a leading Markdown heading (it's already shown
    as the section label) and collapse whitespace so nothing reads as raw markup."""
    body = _LEAD_HEADING.sub("", text, count=1).strip() or text
    body = re.sub(r"^\s*#{1,6}\s+", "", body)  # heading-only chunk: strip the '#'
    return " ".join(body.split())


def render_answer(text, sources):
    render_markdown(text)
    if not sources:
        return
    docs = ", ".join(dict.fromkeys(s.get("doc", "") for s in sources))
    pills = "".join(
        f"<span class='pill'>{s.get('label', '')}"
        + (f" · {_pages_str(s.get('pages'))}" if s.get("pages") else "") + "</span>"
        for s in sources)
    st.markdown(f"<div class='srcline'>Grounded in <b>{docs}</b></div>"
                f"<div>{pills}</div>", unsafe_allow_html=True)
    with st.expander("Read the source passages"):
        for s in sources:
            snippet = _passage(s.get("text", ""))
            snippet = (snippet[:420] + "…") if len(snippet) > 420 else snippet
            sec = f"<div class='src-sec'>{s['section']}</div>" if s.get("section") else ""
            st.markdown(
                f"<div class='src'><div class='src-head'>"
                f"<span class='badge'>{s.get('label', '')}</span>"
                f"<span class='src-doc'>{s.get('doc', '')}</span>"
                f"<span class='src-page'>{_pages_str(s.get('pages'))}</span></div>"
                f"{sec}<div class='src-text'>“{snippet}”</div></div>",
                unsafe_allow_html=True)


store = get_store()
docs = list_docs(store)

# ---- sidebar: the knowledge base -------------------------------------------
with st.sidebar:
    st.markdown("### Your documents")
    if docs:
        for name, info in sorted(docs.items()):
            pages = max(info["pages"]) if info["pages"] else 0
            st.markdown(f"<div class='doc-row'><span>{name}</span>"
                        f"<span>{pages}p · {info['chunks']} chunks</span></div>",
                        unsafe_allow_html=True)
    else:
        st.caption("No documents yet. Add one below.")

    st.markdown("###")
    up = st.file_uploader("Add a PDF", type="pdf", label_visibility="collapsed")
    max_pages = st.number_input("Pages to read (0 = all)", 0, value=0, step=1,
                                help="Cap pages to keep big PDFs fast and cheap.")
    if st.button("Add to knowledge base", disabled=up is None, width="stretch",
                 type="primary"):
        try:
            with st.spinner("Reading, splitting and indexing…"):
                ingest_upload(store, up.name, up.getvalue(), max_pages)
            st.success(f"Added {up.name}.")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not add it: {exc}")

    with st.expander("Manage"):
        if SAMPLE not in {Path(d).stem for d in docs}:
            if st.button("Load the sample story", width="stretch"):
                with st.spinner("Loading the sample…"):
                    ingest_sample(store)
                st.rerun()
        if st.button("Clear everything", width="stretch"):
            store.reset()
            st.session_state.pop("messages", None)
            st.rerun()
    st.caption(f"Model: {settings.chat_model}")

# ---- main: hero + chat ------------------------------------------------------
st.markdown("<div class='hero'><h1>Noema</h1>"
            "<p>Add your documents. Ask anything. Get answers with their sources.</p></div>",
            unsafe_allow_html=True)

if not docs:
    st.info("Your knowledge base is empty.")
    c = st.columns(2)
    with c[0]:
        st.markdown("**Start fast** — load a short sample story and ask about it.")
        if st.button("Load the sample story", type="primary", width="stretch"):
            with st.spinner("Loading the sample…"):
                ingest_sample(store)
            st.rerun()
    with c[1]:
        st.markdown("**Use your own** — add a PDF from the sidebar on the left.")
    st.stop()

st.session_state.setdefault("messages", [])

# suggested questions, only before the first question
SUGGESTIONS = (["What shifted the crystal frequency, and to what?",
                "Contrast the motivations of Thorne and Vance.",
                "What are the three characters and their ages?"]
               if SAMPLE in {Path(d).stem for d in docs}
               else ["Summarize the documents.",
                     "What are the key points?",
                     f"What is {sorted(docs)[0]} about?"])

if not st.session_state["messages"]:
    st.caption("Try one of these:")
    cols = st.columns(len(SUGGESTIONS))
    for col, s in zip(cols, SUGGESTIONS):
        if col.button(s, key=f"sg_{s}", width="stretch"):
            st.session_state["pending_q"] = s
            st.rerun()

for m in st.session_state["messages"]:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            render_answer(m["content"], m.get("sources", []))
        else:
            st.markdown(m["content"])

prompt = st.chat_input("Ask anything about your documents…")
q = prompt or st.session_state.pop("pending_q", None)

if q:
    st.session_state["messages"].append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching your documents…"):
                tr = search_trace(q, k=5, dense_k=20, bm25_k=20, rerank_mode="off",
                                  domain_id=DOMAIN, store=store)
                ans = answer_from(q, tr.final)
            sources = [{"label": f"S{i + 1}", "doc": c.doc_id, "pages": c.pages,
                        "section": c.section, "text": c.text}
                       for i, c in enumerate(ans.sources)]
            render_answer(ans.text, sources)
            st.session_state["messages"].append(
                {"role": "assistant", "content": ans.text, "sources": sources})
        except Exception as exc:  # noqa: BLE001
            st.error(f"Something went wrong: {exc}")

# ---- the test report, tucked away at the bottom (advanced) ------------------
entries = load_log()
if entries:
    with st.expander("Test report (advanced)"):
        groups = {v: [e for e in entries if e.get("verdict") == v]
                  for v in ("win", "fail", "partial")}
        m = st.columns(3)
        m[0].metric("Wins", len(groups["win"]))
        m[1].metric("Fails", len(groups["fail"]))
        m[2].metric("Partial", len(groups["partial"]))
        for v in ("fail", "partial", "win"):
            for e in groups[v]:
                st.markdown(f"- {verdict_badge(v)} **{e.get('scope', '')}** — "
                            f"{e.get('note') or '(no note)'}")
