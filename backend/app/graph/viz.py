"""Render a GraphSnapshot to an interactive vis-network graph.

Drag nodes, zoom, hover for detail. Directed edges carry the relationship label;
a current fact is a solid green arrow, an invalidated/expired fact is a dashed grey
arrow (kept, not hidden — the whole point of a temporal graph). vis-network is loaded
from a CDN; if it can't load, a plain table of the same facts is shown instead so the
data is never invisible.
"""

from __future__ import annotations

import html
import json

from app.graph.base import GraphSnapshot

_VIS = "https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"
_LIVE = "#3ddc97"
_DEAD = "#5a6286"

_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;background:#0e1220;font-family:system-ui,-apple-system,sans-serif}
  #net{width:100%;height:__HEIGHT__px;background:#0e1220;border:1px solid #28304a;border-radius:14px}
  #legend{position:absolute;left:14px;top:12px;font-size:12px;color:#9aa3c0;z-index:5;
    background:#0e1220cc;padding:5px 9px;border-radius:8px}
  #legend b{display:inline-block;width:22px;height:0;vertical-align:middle;margin-right:5px}
  #title{position:absolute;right:14px;top:12px;font-size:12px;color:#cdd6ff;font-weight:700;z-index:5}
  #fallback{display:none;color:#c7cde4;padding:14px;font-size:13px}
  #fallback table{width:100%;border-collapse:collapse}
  #fallback td{border-bottom:1px solid #28304a;padding:5px 7px}
  .empty{color:#9aa3c0;text-align:center;padding:54px}
</style></head>
<body>
<div style="position:relative">
  <div id="title">__TITLE__</div>
  <div id="legend">
    <span><b style="border-top:3px solid __LIVE__"></b>current</span> &nbsp;
    <span><b style="border-top:2px dashed __DEAD__"></b>invalidated</span>
  </div>
  <div id="net"></div>
  <div id="fallback">__FALLBACK__</div>
</div>
<script src="__VIS__" onerror="window.__visFailed=true"></script>
<script>
(function(){
  var nodes = __NODES__, edges = __EDGES__, options = __OPTIONS__;
  function fail(){ document.getElementById('net').style.display='none';
                  document.getElementById('fallback').style.display='block'; }
  function draw(){
    if (window.__visFailed || typeof vis === 'undefined'){ return fail(); }
    try{
      var net = new vis.Network(document.getElementById('net'),
        { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) }, options);
      net.once('stabilizationIterationsDone', function(){ net.setOptions({physics:false}); });
    }catch(e){ fail(); }
  }
  if (document.readyState === 'complete') draw();
  else window.addEventListener('load', draw);
})();
</script>
</body></html>"""


def _empty_doc(height: int) -> str:
    return (f'<div style="height:{height}px;background:#0e1220;border:1px solid #28304a;'
            f'border-radius:14px;display:flex;align-items:center;justify-content:center;'
            f'color:#9aa3c0;font-family:system-ui">The graph is empty — add some knowledge '
            f'to see it build.</div>')


def render_html(snapshot: GraphSnapshot, *, height: int = 520, title: str = "") -> str:
    if not snapshot.nodes:
        return _empty_doc(height)

    names = {n.uuid: n.name for n in snapshot.nodes}

    nodes = [{
        "id": n.uuid,
        "label": n.name,
        "title": n.name + (("\n" + n.summary) if n.summary else ""),
        "shape": "dot", "size": 15,
        "color": {"background": "#1a2a4f", "border": "#4f8cff",
                  "highlight": {"background": "#27406e", "border": "#7c3aed"}},
        "font": {"color": "#dce8ff", "size": 14, "face": "system-ui"},
        "borderWidth": 2,
    } for n in snapshot.nodes]

    edges = []
    for e in snapshot.edges:
        live = e.is_current
        when = ""
        if e.valid_at:
            when += "\nvalid " + e.valid_at[:10]
        if e.invalid_at:
            when += "  →  invalid " + e.invalid_at[:10]
        edges.append({
            "from": e.source_uuid, "to": e.target_uuid,
            "label": e.name or "",
            "title": (e.fact or f"{names.get(e.source_uuid,'?')} {e.name} {names.get(e.target_uuid,'?')}")
                     + ("\n● current" if live else "\n○ INVALIDATED") + when,
            "arrows": "to",
            "dashes": (not live),
            "width": 2.5 if live else 1.4,
            "color": {"color": _LIVE if live else _DEAD,
                      "highlight": "#7c3aed", "hover": "#7c3aed", "opacity": 1.0 if live else 0.65},
            "font": {"color": "#bfeede" if live else "#7a83a6", "size": 11.5,
                     "strokeWidth": 4, "strokeColor": "#0e1220", "align": "middle"},
            "smooth": {"enabled": True, "type": "dynamic"},
        })

    options = {
        "nodes": {"shadow": False},
        "edges": {"selectionWidth": 2},
        "physics": {"solver": "barnesHut",
                    "barnesHut": {"gravitationalConstant": -9000, "springLength": 140,
                                  "springConstant": 0.045, "damping": 0.5, "avoidOverlap": 0.4},
                    "stabilization": {"iterations": 180}},
        "interaction": {"hover": True, "tooltipDelay": 120, "zoomView": True, "dragView": True,
                        "navigationButtons": False, "multiselect": False},
    }

    # plain-table fallback (CDN blocked / vis failed to load)
    rows = "".join(
        f"<tr><td>{html.escape(names.get(e.source_uuid,'?'))}</td>"
        f"<td style='color:#9db8ff'>{html.escape(e.name or '')}</td>"
        f"<td>{html.escape(names.get(e.target_uuid,'?'))}</td>"
        f"<td style='color:{_LIVE if e.is_current else _DEAD}'>"
        f"{'current' if e.is_current else 'invalidated'}</td></tr>"
        for e in snapshot.edges)
    fallback = (f"<b>Interactive view couldn't load (offline?). Facts:</b>"
                f"<table>{rows or '<tr><td>no facts yet</td></tr>'}</table>")

    return (_TEMPLATE
            .replace("__HEIGHT__", str(height))
            .replace("__TITLE__", html.escape(title))
            .replace("__LIVE__", _LIVE).replace("__DEAD__", _DEAD)
            .replace("__VIS__", _VIS)
            .replace("__NODES__", json.dumps(nodes))
            .replace("__EDGES__", json.dumps(edges))
            .replace("__OPTIONS__", json.dumps(options))
            .replace("__FALLBACK__", fallback))
