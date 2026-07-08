"""Noema — Graph Workbench: text or PDF → live knowledge graph → ask & update.

Runs on the unified backend venv (Python 3.12):
    backend/.venv/bin/python -m streamlit run tests/graph_workbench.py

Two modes (Text / PDF). Three panes:
  LEFT   — the source: text you write, or a PDF's extracted text (and the PDF itself).
  MIDDLE — the live knowledge graph (updates in real time after every action).
  RIGHT  — top: ask the graph and see what it retrieves; bottom: add/correct text → graph.

Extraction is bounded by a SOTA auto-induced per-domain schema (see app/graph/schema.py):
the first build samples the source, derives this domain's entity/relationship types, and
all extraction is guided by them.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from streamlit.components.v1 import html as st_html

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.graph import GraphMemory, GraphSnapshot, graph_config, render_html  # noqa: E402
from app.graph.schema import induce_schema, save_schema, schema_instructions  # noqa: E402

LAB_MODEL = settings.parse_model or settings.chat_model
# Models offered for graph generation. The configured strong/fast models come first;
# on OpenAI we add a few common extraction-capable ones. (llmaas: only the configured
# names exist on the gateway, so we don't invent extras there.)
_CANDIDATES = [settings.parse_model, settings.chat_model]
if settings.provider == "openai":
    _CANDIDATES += ["gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-4o"]
MODEL_OPTIONS = [m for m in dict.fromkeys(_CANDIDATES) if m]
DOMAINS = {"text": "wb_text", "pdf": "wb_pdf"}
SAVED = ROOT / "results" / "graph_saved"

st.set_page_config(page_title="Noema · Graph Workbench", page_icon="◆", layout="wide")
st.markdown("""
<style>
#MainMenu, footer {visibility:hidden}
/* full-bleed: span the whole viewport, panels hug the edges */
.block-container {padding:0.7rem 1.4rem 0 !important; max-width:100% !important}
h1.hdr {font-size:1.6rem;font-weight:800;letter-spacing:-.03em;margin:.1rem 0 .2rem;
  background:linear-gradient(95deg,#2563eb,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.pane-h {font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#6b7280;
  margin:.2rem 0 .5rem;border-bottom:1px solid #eceef2;padding-bottom:.3rem}
.badge {display:inline-block;font-size:.72rem;font-weight:700;border-radius:999px;padding:2px 9px;margin:1px}
.b-ok {background:#ecfdf5;color:#047857;border:1px solid #a7f3d0}
.b-info {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.fact {border:1px solid #eceef2;border-left:3px solid #10b981;border-radius:9px;padding:.45rem .7rem;margin:.35rem 0;background:#fff}
.fact.dead {border-left-color:#9ca3af;background:#fafafa}
.fact .rel {font-family:ui-monospace,monospace;font-size:.74rem;color:#4338ca;font-weight:600}
.fact .txt {color:#374151;font-size:.86rem;margin:.1rem 0}
.fact .meta {font-size:.68rem;color:#9ca3af}
.srctext {background:#fbfbfd;border:1px solid #eceef2;border-radius:10px;padding:.7rem .9rem;
  font-size:.82rem;color:#374151;height:300px;overflow:auto;white-space:pre-wrap;line-height:1.5}
.stButton>button {border-radius:9px}
</style>
""", unsafe_allow_html=True)


# ---- async runtime: one loop thread per domain ------------------------------
class _GraphRuntime:
    def __init__(self, domain, model):
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()

        async def _make():
            m = GraphMemory(domain, extract_model=model)
            await m.build()
            return m

        self.mem = self.run(_make())

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


@st.cache_resource
def runtime(domain: str, model: str) -> _GraphRuntime:
    # Cached per (domain, model): picking a different model builds a fresh memory with
    # that extractor, connected to the SAME graph — existing data stays, new extraction
    # uses the chosen model.
    return _GraphRuntime(domain, model)


# ---- helpers ----------------------------------------------------------------
def ingest_text(rt: _GraphRuntime, text: str, *, induce: bool, model: str):
    """Optionally induce a schema from the text, then ingest it as an episode."""
    if induce and not rt.mem.schema:
        sch = induce_schema(text, domain=rt.mem.domain_id, model=model)
        if sch.entity_types:
            save_schema(sch)
            rt.mem.apply_schema(sch)
    return rt.run(rt.mem.add_episode(text, reference_time=datetime.now(timezone.utc)))


@st.cache_data(show_spinner=False)
def parse_pdf_cached(data: bytes, name: str):
    from app import parsing
    doc = parsing.parse_document(data, name)
    return {"pages": doc.pages, "page_markdown": list(doc.page_markdown), "markdown": doc.markdown}


def render_facts(facts):
    if not facts:
        st.caption("No facts retrieved.")
        return
    for f in facts:
        d = f.to_dict() if not isinstance(f, dict) else f
        cls = "fact" if d.get("is_current", True) else "fact dead"
        tag = "current" if d.get("is_current", True) else "invalidated"
        st.markdown(
            f"<div class='{cls}'><div class='rel'>{d.get('source','?')} —{d.get('name','')}→ "
            f"{d.get('target','?')}</div><div class='txt'>{d.get('fact','')}</div>"
            f"<div class='meta'>{tag}"
            f"{(' · valid ' + d['valid_at'][:10]) if d.get('valid_at') else ''}"
            f"{(' · ' + str(len(d.get('episodes',[]))) + ' source(s)') if d.get('episodes') else ''}"
            f"</div></div>", unsafe_allow_html=True)


def render_graph(rt, height=720):
    try:
        snap = rt.run(rt.mem.snapshot())
    except Exception as exc:  # noqa: BLE001
        st.error(f"Couldn't read the graph: {exc}")
        return GraphSnapshot()
    st_html(render_html(snap, height=height), height=height + 16)
    cur = sum(e.is_current for e in snap.edges)
    st.caption(f"{len(snap.nodes)} entities · {len(snap.edges)} facts "
               f"({cur} current, {len(snap.edges)-cur} invalidated) · drag · zoom · hover")
    return snap


def schema_badges(rt):
    sch = rt.mem.schema
    if not sch:
        st.caption("No schema yet — the first build will induce one from your source.")
        return
    st.markdown("".join(f"<span class='badge b-info'>{t.name}</span>" for t in sch.entity_types),
                unsafe_allow_html=True)


# ---- save / load graphs (for presenting later) ------------------------------
def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9 _-]+", "", name or "").strip() or "graph"


def save_graph(name, domain, snap, source, schema):
    SAVED.mkdir(parents=True, exist_ok=True)
    payload = {"name": name, "domain": domain,
               "saved_at": datetime.now(timezone.utc).isoformat(),
               "source": (source or "")[:4000],
               "schema": schema.to_dict() if schema else None,
               "snapshot": snap.to_dict()}
    (SAVED / f"{_safe(name)}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                               encoding="utf-8")


def list_saved():
    out = []
    for f in sorted(SAVED.glob("*.json")) if SAVED.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"stem": f.stem, "name": d.get("name", f.stem),
                        "nodes": len(d["snapshot"]["nodes"]), "edges": len(d["snapshot"]["edges"])})
        except Exception:  # noqa: BLE001
            continue
    return out


def load_saved(stem):
    d = json.loads((SAVED / f"{stem}.json").read_text(encoding="utf-8"))
    return d, GraphSnapshot.from_dict(d["snapshot"])


# ---- header + mode ----------------------------------------------------------
st.markdown("<h1 class='hdr'>Graph Workbench</h1>", unsafe_allow_html=True)
top = st.columns([1.2, 1.6, 2.2])
with top[0]:
    mode = st.radio("Mode", ["✍️ Text", "📄 PDF"], horizontal=True, label_visibility="collapsed")
with top[1]:
    model = st.selectbox(
        "Graph model", MODEL_OPTIONS, index=0, label_visibility="collapsed",
        help="The model that GENERATES the graph from text — entity/relationship "
             "extraction and schema induction. Stronger = more complete; mini = faster/cheaper.")
is_pdf = mode.endswith("PDF")
domain = DOMAINS["pdf" if is_pdf else "text"]
rt = runtime(domain, model)
with top[2]:
    st.markdown(f"<div style='text-align:right;padding-top:.3rem'>"
                f"<span class='badge b-ok'>backend: {graph_config.backend}</span>"
                f"<span class='badge b-info'>graph model: {model}</span>"
                f"<span class='badge b-info'>domain: {domain}</span></div>", unsafe_allow_html=True)

left, mid, right = st.columns([1, 2.5, 1.2], gap="medium")


def _added(res):
    """Inline feedback co-located with the action; warns when nothing was extractable."""
    if res and (len(res.nodes) or len(res.edges)):
        st.success(f"✓ extracted {len(res.nodes)} entities, {len(res.edges)} facts — "
                   "the graph in the middle is updated.")
    else:
        st.warning("Nothing extractable found — try longer or more specific text.")


# Render order is deliberate: LEFT and RIGHT can mutate the graph, so the MIDDLE pane
# (the graph) is written LAST — it then reflects the change in the SAME run (no second
# rerun), and each confirmation shows right next to the action that caused it.

# ---- LEFT — source + build --------------------------------------------------
with left:
    if is_pdf:
        st.markdown("<div class='pane-h'>📄 Source · PDF</div>", unsafe_allow_html=True)
        up = st.file_uploader("PDF", type="pdf", label_visibility="collapsed")
        if up:
            data = up.getvalue()
            with st.spinner("Reading the PDF (vision-routed where needed)…"):
                parsed = parse_pdf_cached(data, up.name)
            st.session_state[f"{domain}_text"] = parsed["markdown"]
            st.caption(f"{parsed['pages']} pages parsed.")
            with st.expander("Open / read the original PDF"):
                b64 = base64.b64encode(data).decode()
                st_html(f"<iframe src='data:application/pdf;base64,{b64}' width='100%' height='420' "
                        f"style='border:1px solid #28304a;border-radius:8px'></iframe>", height=430)
                st.download_button("Download PDF", data, file_name=up.name)
            st.markdown("**Extracted text**")
            st.markdown(f"<div class='srctext'>{parsed['markdown'][:6000]}</div>", unsafe_allow_html=True)
            n_pages = parsed["pages"]
            if st.button(f"Build graph from this PDF ({n_pages} pages)", type="primary", width="stretch"):
                pages = parsed["page_markdown"]
                total = 0
                with st.spinner(f"Inducing schema + ingesting {n_pages} page(s)… (minutes for a long PDF)"):
                    if not rt.mem.schema:
                        sch = induce_schema(parsed["markdown"], domain=domain, model=model)
                        if sch.entity_types:
                            save_schema(sch); rt.mem.apply_schema(sch)
                    prog = st.progress(0.0)
                    for i, pg in enumerate(pages, 1):
                        if pg.strip():
                            r = rt.run(rt.mem.add_episode(pg, name=f"page-{i}",
                                                          reference_time=datetime.now(timezone.utc)))
                            total += len(getattr(r, "nodes", []) or [])
                        prog.progress(i / max(1, len(pages)))
                st.success(f"✓ built from {up.name} — extracted ~{total} entities. See the graph →")
        else:
            st.info("Upload a PDF to read it and build its graph.")
    else:
        st.markdown("<div class='pane-h'>✍️ Source · Text</div>", unsafe_allow_html=True)
        txt = st.text_area("Source text", key=f"{domain}_text", height=300,
                           placeholder="Paste or write text on your domain (e.g. a finance note)…",
                           label_visibility="collapsed")
        if st.button("Build graph from this text", type="primary", width="stretch",
                     disabled=not (txt or "").strip()):
            with st.spinner(f"Inducing schema + extracting with {model}…"):
                res = ingest_text(rt, txt.strip(), induce=True, model=model)
            _added(res)
    st.markdown("<div class='pane-h' style='margin-top:1rem'>Induced schema</div>", unsafe_allow_html=True)
    schema_badges(rt)
    if rt.mem.schema and st.button("Re-induce schema from source", width="stretch"):
        src = st.session_state.get(f"{domain}_text", "")
        if src.strip():
            with st.spinner(f"Re-inducing schema with {model}…"):
                sch = induce_schema(src, domain=domain, model=model)
                if sch.entity_types:
                    save_schema(sch); rt.mem.apply_schema(sch)
            st.success("Schema re-induced — applies to new additions.")

    st.markdown("<div class='pane-h' style='margin-top:1rem'>Saved graphs</div>", unsafe_allow_html=True)
    saved = list_saved()
    if not saved:
        st.caption("Build a graph, then 💾 Save it (under the graph) to keep it for later.")
    for s in saved:
        c = st.columns([3, 1.1, 0.6])
        c[0].markdown(f"<div style='font-size:.85rem;font-weight:600'>{s['name']}</div>"
                      f"<div style='font-size:.7rem;color:#9ca3af'>{s['nodes']} nodes · {s['edges']} edges</div>",
                      unsafe_allow_html=True)
        if c[1].button("Show", key=f"show_{s['stem']}", width="stretch"):
            st.session_state[f"{domain}_viewing"] = s["stem"]
            st.rerun()
        if c[2].button("✕", key=f"del_{s['stem']}", help="Delete this saved graph"):
            (SAVED / f"{s['stem']}.json").unlink(missing_ok=True)
            st.rerun()

# ---- RIGHT — ask + update ---------------------------------------------------
with right:
    st.markdown("<div class='pane-h'>🔎 Ask the graph</div>", unsafe_allow_html=True)
    q = st.text_input("Ask", key=f"{domain}_q", placeholder="What does the graph say about…?",
                      label_visibility="collapsed")
    if q:
        with st.spinner("Hybrid search (semantic + BM25 + graph)…"):
            facts = rt.run(rt.mem.search(q, limit=6))
        st.caption(f"Retrieved {len(facts)} fact(s):")
        render_facts(facts)

    st.markdown("<div class='pane-h' style='margin-top:1.2rem'>✚ Add / correct a fact</div>",
                unsafe_allow_html=True)
    with st.form(f"{domain}_add", clear_on_submit=True):
        new = st.text_area("Add", height=90, label_visibility="collapsed",
                           placeholder="e.g. The CEO stepped down in March 2026.")
        if st.form_submit_button("Update the graph", type="primary", width="stretch") and new.strip():
            try:
                with st.spinner("Extracting & merging (contradictions get invalidated)…"):
                    res = rt.run(rt.mem.add_episode(new.strip(), reference_time=datetime.now(timezone.utc)))
                _added(res)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Update failed: {exc}")

# ---- MIDDLE — the graph, written LAST so it reflects the actions above -------
def _facts_table(snap):
    names = {n.uuid: n.name for n in snap.nodes}
    st.dataframe([{"source": names.get(e.source_uuid, "?"), "relation": e.name,
                   "target": names.get(e.target_uuid, "?"),
                   "state": "current" if e.is_current else "invalidated"}
                  for e in snap.edges] or [{"source": "—", "relation": "", "target": "", "state": ""}],
                 width="stretch", hide_index=True)


with mid:
    viewing = st.session_state.get(f"{domain}_viewing")
    if viewing and (SAVED / f"{viewing}.json").exists():
        # presentation view of a saved graph — fills the same big canvas
        d, vsnap = load_saved(viewing)
        st.markdown(f"<div class='pane-h'>🗂️ Saved graph · {d.get('name', viewing)}</div>",
                    unsafe_allow_html=True)
        st_html(render_html(vsnap, height=720), height=736)
        cur = sum(e.is_current for e in vsnap.edges)
        st.caption(f"{len(vsnap.nodes)} entities · {len(vsnap.edges)} facts · saved "
                   f"{d.get('saved_at','')[:10]} — presentation view")
        c = st.columns([2, 1])
        if c[0].button("← Back to the live graph", width="stretch"):
            st.session_state[f"{domain}_viewing"] = None
            st.rerun()
        with c[1].popover("Facts table", use_container_width=True):
            _facts_table(vsnap)
    else:
        st.markdown("<div class='pane-h'>🕸️ Knowledge graph · live</div>", unsafe_allow_html=True)
        snap = render_graph(rt)
        cc = st.columns(3)
        if cc[0].button("Clear graph", width="stretch"):
            rt.run(rt.mem.reset())
            st.rerun()
        with cc[1].popover("💾 Save", use_container_width=True):
            nm = st.text_input("Name this graph", key=f"{domain}_savename",
                               placeholder="e.g. Spotify demo")
            if st.button("Save graph", key=f"{domain}_savebtn", type="primary", width="stretch",
                         disabled=not (nm or "").strip() or not snap.nodes):
                save_graph(nm.strip(), domain, snap,
                           st.session_state.get(f"{domain}_text", ""), rt.mem.schema)
                st.success(f"Saved “{nm.strip()}” — find it in ‘Saved graphs’ on the left.")
        with cc[2].popover("Facts table", use_container_width=True):
            _facts_table(snap)
