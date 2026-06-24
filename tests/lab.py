"""Noema Lab — interactive testbench (multipage Streamlit).

Run:
    backend/.venv/bin/python -m streamlit run tests/lab.py

Pages (sidebar): Parser, Chunker. Each has three tabs — How it works, Saved tests,
Live run. This Home page is the overview and the shared test report.
"""

from __future__ import annotations

import streamlit as st

from lab_common import load_log, style, verdict_badge

st.set_page_config(page_title="Noema Lab", layout="wide")
style()

st.title("Noema Lab")
st.caption("Interactive testbench for the ingestion pipeline. Independent of the product; "
           "imports the app modules read-only.")

c = st.columns(2)
with c[0]:
    st.subheader("Parser")
    st.write("PDF to Markdown + LaTeX via the vision model, with per-page routing "
             "(free text layer vs vision). Open it from the sidebar.")
with c[1]:
    st.subheader("Chunker")
    st.write("Markdown to provenance-tagged chunks (document, page, section). "
             "Open it from the sidebar.")

st.caption("Each tool page has three tabs: **How it works** (diagram + the real code), "
           "**Saved tests** (browse cached results, add your own), **Live run** "
           "(watch the mechanism execute, with timing).")

# ---- the shared test report (wins / fails resume) ---------------------------
st.divider()
st.subheader("Test report")
entries = load_log()
groups = {v: [e for e in entries if e.get("verdict") == v] for v in ("win", "fail", "partial")}
m = st.columns(4)
m[0].metric("Total", len(entries))
m[1].metric("Wins", len(groups["win"]))
m[2].metric("Fails", len(groups["fail"]))
m[3].metric("Partial", len(groups["partial"]))

tools = sorted({e.get("tool", "?") for e in entries})
flt = st.multiselect("Filter by tool", tools, default=tools) if tools else []

for v in ("fail", "partial", "win"):  # fails first — most actionable
    bucket = [e for e in groups[v] if not flt or e.get("tool", "?") in flt]
    if not bucket:
        continue
    st.markdown(f"#### {verdict_badge(v)} — {v.capitalize()} ({len(bucket)})")
    for e in bucket:
        src = e.get("input", {}).get("source") if isinstance(e.get("input"), dict) else None
        meta = " · ".join(x for x in (e.get("tool"), src, e.get("pdf"), e.get("date")) if x)
        st.markdown(f"- **{e.get('scope', '')}** — {e.get('note') or '(no note)'}  \n"
                    f"  <span style='color:#888;font-size:0.85em'>{meta}</span>",
                    unsafe_allow_html=True)
        io = {k: e[k] for k in ("input", "output") if isinstance(e.get(k), dict)}
        if io:
            with st.expander("input / output"):
                st.json(io)

if not entries:
    st.info("No results logged yet. Run a tool and use 'Log run'.")
