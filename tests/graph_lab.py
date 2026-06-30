"""Noema — Graph Lab: see the temporal knowledge graph, test it live, replay edge cases.

Runs on the unified backend venv (Python 3.12 — base + graph in one process):

    backend/.venv/bin/python -m streamlit run tests/graph_lab.py

Standalone on purpose — this is the graph *before* it's wired into the chatbot. Add a
sentence, watch the graph extract entities and relationships; add a contradicting one,
watch the old fact get invalidated (not deleted); ask a question, get facts back with
their temporal validity. The bottom section replays the saved edge-case runs offline.
"""

from __future__ import annotations

import asyncio
import json
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

DOMAIN = "playground"
RUNS = ROOT / "results" / "graph_runs"
# Use the strong extractor — graph quality (and reliable temporal invalidation) depends
# on it; a weak model produces a sparse graph and misses the subject/relationship.
LAB_MODEL = settings.parse_model or settings.chat_model

st.set_page_config(page_title="Noema · Graph Lab", page_icon="◆", layout="centered")

st.markdown("""
<style>
#MainMenu, footer {visibility:hidden}
.block-container {padding-top:2rem; max-width:880px}
.hero {text-align:center; margin:.2rem 0 1.1rem}
.hero h1 {font-size:2.5rem; font-weight:800; letter-spacing:-.04em; margin:0;
  background:linear-gradient(95deg,#2563eb,#7c3aed); -webkit-background-clip:text;
  -webkit-text-fill-color:transparent}
.hero p {color:#6b7280; font-size:1rem; margin:.25rem 0 0}
.badge {display:inline-block;font-size:.74rem;font-weight:700;border-radius:999px;
  padding:3px 11px;margin:2px}
.b-emb {background:#ecfdf5;color:#047857;border:1px solid #a7f3d0}
.b-srv {background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.fact {border:1px solid #eceef2;border-left:3px solid #10b981;border-radius:10px;
  padding:.55rem .8rem;margin:.4rem 0;background:#fff}
.fact.dead {border-left-color:#9ca3af;background:#fafafa}
.fact .rel {font-family:ui-monospace,monospace;font-size:.78rem;color:#4338ca;font-weight:600}
.fact .txt {color:#374151;font-size:.92rem;margin:.15rem 0}
.fact .meta {font-size:.72rem;color:#9ca3af}
.tag {font-size:.68rem;font-weight:700;border-radius:5px;padding:1px 7px;margin-left:6px}
.tag.live {background:#d1fae5;color:#065f46}
.tag.dead {background:#f3f4f6;color:#6b7280}
.stButton>button {border-radius:10px}
</style>
""", unsafe_allow_html=True)


# ---- async runtime: one event loop in a dedicated background thread ----------
# Streamlit reruns the script in its own threads; calling run_until_complete from
# there is fragile (silent no-ops / hangs). Instead we own ONE loop in ONE thread for
# the whole session and submit every graph op to it — connections stay bound to it.
class _GraphRuntime:
    def __init__(self, domain: str, model: str):
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
def runtime() -> "_GraphRuntime":
    return _GraphRuntime(DOMAIN, LAB_MODEL)


def run(coro):
    return runtime().run(coro)


def memory() -> GraphMemory:
    return runtime().mem


# ---- header -----------------------------------------------------------------
st.markdown("<div class='hero'><h1>Graph Lab</h1>"
            "<p>A temporal knowledge graph you can poke at — add facts, watch them connect and expire.</p></div>",
            unsafe_allow_html=True)

is_emb = graph_config.backend == "falkor_embedded"
st.markdown(
    f"<div style='text-align:center'><span class='badge {'b-emb' if is_emb else 'b-srv'}'>"
    f"backend: {graph_config.backend}{' (in-process, no server)' if is_emb else ''}</span>"
    f"<span class='badge b-srv'>extractor: {LAB_MODEL}</span></div>",
    unsafe_allow_html=True)


def temporal_tag(f_or_e):
    cur = f_or_e.get("is_current", True) if isinstance(f_or_e, dict) else f_or_e.is_current
    return ("<span class='tag live'>current</span>" if cur
            else "<span class='tag dead'>invalidated</span>")


def render_facts(facts):
    if not facts:
        st.caption("No facts retrieved.")
        return
    for f in facts:
        d = f.to_dict() if not isinstance(f, dict) else f
        cls = "fact" if d.get("is_current", True) else "fact dead"
        window = []
        if d.get("valid_at"):
            window.append("valid " + d["valid_at"][:10])
        if d.get("invalid_at"):
            window.append("→ invalid " + d["invalid_at"][:10])
        st.markdown(
            f"<div class='{cls}'><div class='rel'>{d.get('source','?')} "
            f"—{d.get('name','')}→ {d.get('target','?')}{temporal_tag(d)}</div>"
            f"<div class='txt'>{d.get('fact','')}</div>"
            f"<div class='meta'>{'  ·  '.join(window)}"
            f"{('  ·  ' + str(len(d.get('episodes', []))) + ' source episode(s)') if d.get('episodes') else ''}"
            f"</div></div>", unsafe_allow_html=True)


def show_graph(height=520, title=""):
    try:
        snap = run(memory().snapshot())
    except Exception as exc:  # surface, don't hide
        st.error(f"Couldn't read the graph: {exc}")
        return GraphSnapshot()
    st_html(render_html(snap, title=title, height=height), height=height + 16)
    return snap


def show_table(snap):
    if not snap.edges:
        return
    with st.expander("Graph as a table (facts)"):
        names = {n.uuid: n.name for n in snap.nodes}
        rows = [{"source": names.get(e.source_uuid, "?"), "relation": e.name,
                 "target": names.get(e.target_uuid, "?"),
                 "state": "current" if e.is_current else "invalidated",
                 "valid_at": (e.valid_at or "")[:10], "invalid_at": (e.invalid_at or "")[:10]}
                for e in snap.edges]
        st.dataframe(rows, width="stretch", hide_index=True)


# ---- sidebar ----------------------------------------------------------------
with st.sidebar:
    st.markdown("### Graph Lab")
    st.caption("Add knowledge on the right, then ask the graph about it.")
    if st.button("Load the Kendra demo", width="stretch", type="primary"):
        with st.spinner("Ingesting three episodes over Jan→Aug…"):
            run(memory().reset())
            run(memory().add_episode(
                "Kendra Walsh's favorite shoe brand is Adidas. She wears Adidas every day.",
                name="adidas", reference_time=datetime(2026, 1, 3, tzinfo=timezone.utc)))
            run(memory().add_episode(
                "Kendra Walsh joined Acme as a product designer.",
                name="acme", reference_time=datetime(2026, 3, 10, tzinfo=timezone.utc)))
            run(memory().add_episode(
                "Kendra Walsh's favorite shoe brand is now Nike. She no longer likes Adidas.",
                name="nike", reference_time=datetime(2026, 8, 21, tzinfo=timezone.utc)))
        st.success("Loaded. Scroll to the graph — the 'favorite = Adidas' fact is invalidated.")
        st.rerun()
    if st.button("Clear the graph", width="stretch"):
        with st.spinner("Clearing…"):
            run(memory().reset())
        st.rerun()
    st.divider()
    st.caption("Runs on the isolated 3.12 graph venv. Backend is swappable to a "
               "server via GRAPH_BACKEND in .env — no code change.")


# ---- live: add knowledge ----------------------------------------------------
st.markdown("#### ➊ Add knowledge")
with st.form("add", clear_on_submit=True):
    body = st.text_area("A sentence or short paragraph to fold into the graph",
                        placeholder="e.g. Ada Lovelace worked with Charles Babbage on the Analytical Engine.",
                        height=90)
    c = st.columns([1, 1])
    when = c[0].date_input("When was this true? (event time)", value=datetime.now().date())
    submitted = c[1].form_submit_button("Add to graph", width="stretch", type="primary")
    if submitted and body.strip():
        try:
            with st.spinner("Extracting entities & relationships… (the strong model takes ~20–40s)"):
                res = run(memory().add_episode(
                    body.strip(),
                    reference_time=datetime(when.year, when.month, when.day, tzinfo=timezone.utc)))
            st.success(f"Added — extracted {len(res.nodes)} entit{'y' if len(res.nodes)==1 else 'ies'} "
                       f"and {len(res.edges)} fact(s). The graph below is updated.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Add failed: {type(exc).__name__}: {exc}")
    elif submitted:
        st.warning("Type a sentence first.")

# ---- the graph ---------------------------------------------------------------
st.markdown("#### ➋ The graph")
snap = show_graph(title="")
st.caption(f"{len(snap.nodes)} entities · {len(snap.edges)} facts "
           f"({sum(e.is_current for e in snap.edges)} current, "
           f"{sum(not e.is_current for e in snap.edges)} invalidated). "
           f"Drag nodes · scroll to zoom · hover for detail.")
show_table(snap)

# ---- live: ask ---------------------------------------------------------------
st.markdown("#### ➌ Ask the graph")
q = st.text_input("Question", placeholder="What does Kendra like?", label_visibility="collapsed")
if q:
    with st.spinner("Hybrid search (semantic + BM25 + graph traversal)…"):
        facts = run(memory().search(q, limit=8))
    render_facts(facts)

# ---- replay saved edge-case runs --------------------------------------------
st.markdown("#### ➍ Edge-case runs (saved results)")
files = sorted(RUNS.glob("*.json")) if RUNS.exists() else []
if not files:
    st.caption("No saved runs yet — run  `backend/.venv/bin/python tests/test_graph.py`  to generate them.")
else:
    pick = st.selectbox("Scenario", [f.stem for f in files])
    data = json.loads((RUNS / f"{pick}.json").read_text(encoding="utf-8"))
    verdict = data.get("verdict", "?")
    color = {"win": "#047857", "partial": "#b45309", "fail": "#b91c1c"}.get(verdict, "#6b7280")
    st.markdown(f"**{data.get('description','')}**  "
                f"<span style='color:{color};font-weight:700'>[{verdict}]</span>", unsafe_allow_html=True)
    for o in data.get("observations", []):
        st.markdown(f"- {o}")
    with st.expander("Episodes ingested"):
        for ep in data.get("episodes", []):
            st.markdown(f"- *{ep['reference_time'][:10]}* — “{ep['body']}”")
    st_html(render_html(GraphSnapshot.from_dict(data["snapshot"]), title=pick, height=420), height=450)
    if data.get("facts"):
        st.caption("Facts retrieved in this run:")
        render_facts(data["facts"])
