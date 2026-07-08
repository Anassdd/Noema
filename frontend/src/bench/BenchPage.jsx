import { useEffect, useRef, useState } from "react";

import {
  deleteDataset,
  downloadStream,
  rejudgeStream,
  getEstimate,
  getGold,
  getReport,
  goldgenStream,
  goldverifyStream,
  listDatasets,
  listRuns,
  prepareDataset,
  putGold,
  reportMdUrl,
  runStream,
} from "../api/bench.js";
import { ghostBtn, primaryBtn, selectStyle, spinner } from "../graph/styles.js";

const CONFIGS = ["closed_book", "rag", "graph", "hybrid"];
const CONFIG_LABELS = {
  closed_book: "Closed-book",
  rag: "Contextual RAG",
  graph: "Graph",
  hybrid: "Hybrid (product)",
};
const TYPE_COLORS = { factoid: "#5cc8ff", synthesis: "#9b8cff", global: "#8fd6c2", null: "#e8a3b8" };

const page = {
  position: "fixed",
  inset: 0,
  overflowY: "auto",
  background:
    "radial-gradient(1000px 500px at 15% -5%, rgba(92,200,255,0.07), transparent 60%)," +
    "radial-gradient(900px 500px at 90% 0%, rgba(155,140,255,0.07), transparent 55%), #070912",
  color: "#e7ecf7",
  fontFamily: "'Inter', system-ui, sans-serif",
};
const card = {
  background: "rgba(13,18,32,0.92)",
  border: "1px solid rgba(120,135,175,0.2)",
  borderRadius: 14,
  padding: 16,
  boxShadow: "0 12px 40px rgba(0,0,0,0.45)",
};
const label = { fontSize: 10.5, letterSpacing: 1.1, textTransform: "uppercase", color: "#7a87a6" };
const input = { ...selectStyle, cursor: "text" };
const th = { textAlign: "left", padding: "6px 10px", color: "#7a87a6", fontSize: 10.5, letterSpacing: 0.8, textTransform: "uppercase", borderBottom: "1px solid rgba(120,135,175,0.18)" };
const td = { padding: "7px 10px", fontSize: 12.5, borderBottom: "1px solid rgba(120,135,175,0.08)", verticalAlign: "top" };

const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function Chip({ text, color = "#7a87a6" }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 600, color, border: `1px solid ${color}44`, background: `${color}18`, borderRadius: 6, padding: "1.5px 7px", whiteSpace: "nowrap" }}>
      {text}
    </span>
  );
}

function Section({ n, title, children, right }) {
  return (
    <div style={{ ...card, marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ width: 22, height: 22, borderRadius: 7, display: "grid", placeItems: "center", fontSize: 11.5, fontWeight: 700, color: "#0a0e1a", background: "#5cc8ff" }}>{n}</span>
        <span style={{ fontSize: 13.5, fontWeight: 650 }}>{title}</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>{right}</div>
      </div>
      {children}
    </div>
  );
}

function HeadlineTable({ rows }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {["config", "n", "judge acc", "lift", "EM", "F1", "evidence", "latency", "tok/q"].map((h) => (
              <th key={h} style={th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.config} style={r.config === "hybrid" ? { background: "rgba(155,140,255,0.06)" } : undefined}>
              <td style={{ ...td, fontWeight: 650 }}>{CONFIG_LABELS[r.config] || r.config}</td>
              <td style={td}>{r.n}</td>
              <td style={{ ...td, color: "#bfe4ff", fontWeight: 650 }}>
                {pct(r.judge_accuracy)}
                {r.judged != null && r.judged < r.n && (
                  <span style={{ color: "#e8a3b8", fontSize: 10.5 }}> ({r.judged}/{r.n} judged)</span>
                )}
              </td>
              <td style={{ ...td, color: (r.lift_over_closed_book ?? 0) > 0 ? "#8fd6c2" : "#e8a3b8" }}>
                {r.lift_over_closed_book == null ? "—" : `${r.lift_over_closed_book > 0 ? "+" : ""}${Math.round(r.lift_over_closed_book * 100)}`}
              </td>
              <td style={td}>{pct(r.em)}</td>
              <td style={td}>{r.f1 ?? "—"}</td>
              <td style={td}>{pct(r.evidence_recall)}</td>
              <td style={td}>{r.latency_ms_avg} ms</td>
              <td style={td}>{r.tokens_per_q}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportView({ report, dataset, onRejudge, busy }) {
  const fusion = report.fusion;
  const health = report.graph_health;
  const u = report.usage_totals;
  const [showGallery, setShowGallery] = useState(false);
  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10, alignItems: "center" }}>
        <Chip text={`run ${report.run_id}`} color="#5cc8ff" />
        <Chip text={`save ${report.build?.save_name}`} color="#9b8cff" />
        <Chip text={`${report.build?.nodes ?? "?"} nodes · ${report.build?.edges ?? "?"} edges · ${report.build?.chunks ?? "?"} chunks`} />
        {health && <Chip text={`${health.orphans} orphans · ${health.duplicate_name_suspects} dup suspects`} color={health.orphans + health.duplicate_name_suspects > 0 ? "#e8c98a" : "#8fd6c2"} />}
        <Chip text={`answers: ${report.answer_model}`} />
        <button style={{ ...ghostBtn, marginLeft: "auto", color: "#8fd6c2", borderColor: "rgba(143,214,194,0.4)" }}
          onClick={onRejudge} disabled={busy !== ""}
          title="Re-score this run's stored answers with the current judge and gold (incl. alternative answers) — costs judging only, never re-runs generation.">
          {busy === "rejudge" ? <span style={spinner} /> : "⚖ Re-judge"}
        </button>
        <a href={reportMdUrl(dataset, report.run_id)} target="_blank" rel="noreferrer" style={{ ...ghostBtn, textDecoration: "none" }}>
          ⬇ report.md
        </a>
      </div>
      {report.verdict && (
        <div style={{ fontSize: 13, color: "#e7ecf7", padding: "10px 14px", marginBottom: 12, background: "rgba(92,200,255,0.08)", border: "1px solid rgba(92,200,255,0.25)", borderRadius: 10 }}>
          {report.verdict}
        </div>
      )}
      <HeadlineTable rows={report.headline || []} />
      {u && (
        <div style={{ fontSize: 11.5, color: "#7a87a6", marginTop: 8 }}>
          tokens — generation {(u.generation?.prompt_tokens ?? 0).toLocaleString()} in / {(u.generation?.completion_tokens ?? 0).toLocaleString()} out
          · judging {(u.judging?.prompt_tokens ?? 0).toLocaleString()} in / {(u.judging?.completion_tokens ?? 0).toLocaleString()} out
          · build cost is separate (see the OpenAI dashboard)
        </div>
      )}

      {Object.keys(report.slices || {}).length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ ...label, marginBottom: 6 }}>By question type</div>
          {Object.entries(report.slices).map(([qtype, rows]) => (
            <div key={qtype} style={{ fontSize: 12, color: "#cdd5ea", marginBottom: 3 }}>
              <Chip text={qtype} color={TYPE_COLORS[qtype]} />{" "}
              {rows.map((r) => `${CONFIG_LABELS[r.config] || r.config} ${pct(r.judge_accuracy)}`).join(" · ")}
            </div>
          ))}
        </div>
      )}

      {fusion && (
        <div style={{ marginTop: 14, fontSize: 12.5, color: "#cdd5ea" }}>
          <div style={{ ...label, marginBottom: 6 }}>Fusion (hybrid)</div>
          graph share of context {pct(fusion.graph_share_of_context)} · accuracy with graph{" "}
          {pct(fusion.accuracy_when_graph_present)} vs without {pct(fusion.accuracy_when_graph_absent)} (
          {fusion.questions_with_graph_context} questions)
        </div>
      )}

      {(report.failure_gallery || []).length > 0 && (
        <div style={{ marginTop: 14 }}>
          <button onClick={() => setShowGallery((s) => !s)}
            style={{ ...label, background: "none", border: "none", cursor: "pointer", padding: 0, marginBottom: 6 }}>
            {showGallery ? "▾" : "▸"} Failure gallery ({report.failure_gallery.length} — 5 worst per config; all failures stay in the run JSON)
          </button>
          {showGallery && report.failure_gallery.map((f, i) => (
            <div key={i} style={{ fontSize: 12, padding: "8px 10px", marginBottom: 6, background: "rgba(232,163,184,0.05)", border: "1px solid rgba(232,163,184,0.15)", borderRadius: 9 }}>
              <div style={{ color: "#e8a3b8", fontWeight: 600, marginBottom: 3 }}>
                {f.qid} · {CONFIG_LABELS[f.config] || f.config} — {f.question}
              </div>
              <div style={{ color: "#8fd6c2" }}>gold: {f.gold}</div>
              <div style={{ color: "#cdd5ea" }}>got: {f.answer || `(error: ${f.error})`}</div>
              {f.note && <div style={{ color: "#7a87a6" }}>judge: {f.note}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BenchPage() {
  const [datasets, setDatasets] = useState(null);
  const [rawDir, setRawDir] = useState("");
  const [selected, setSelected] = useState(null);
  const [cap, setCap] = useState(100000);
  const [gold, setGold] = useState([]);
  const [goldDirty, setGoldDirty] = useState(false);
  const [configs, setConfigs] = useState(["closed_book", "rag", "graph", "hybrid"]);
  const [busy, setBusy] = useState("");
  const [log, setLog] = useState([]);
  const [report, setReport] = useState(null);
  const [runs, setRuns] = useState([]);
  const [est, setEst] = useState(null);
  const [dlUrl, setDlUrl] = useState("");
  const [dlStatus, setDlStatus] = useState("");
  const [dlChoices, setDlChoices] = useState([]);
  const logRef = useRef(null);
  const abortRef = useRef(null);

  const ds = datasets?.find((d) => d.name === selected);

  const refresh = async (keep = true) => {
    const res = await listDatasets();
    setDatasets(res.datasets);
    setRawDir(res.raw_dir);
    if (!keep || !res.datasets.some((d) => d.name === selected)) {
      setSelected(res.datasets[0]?.name ?? null);
    }
  };
  useEffect(() => { refresh(false).catch(() => setDatasets([])); }, []);

  useEffect(() => {
    if (!selected) return;
    setReport(null);
    setLog([]);
    getGold(selected).then((r) => { setGold(r.questions); setGoldDirty(false); }).catch(() => setGold([]));
    listRuns(selected).then((r) => setRuns(r.runs)).catch(() => setRuns([]));
    const prepared = datasets?.find((d) => d.name === selected)?.prepared;
    if (prepared?.cap_tokens) setCap(prepared.cap_tokens);
  }, [selected]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [log]);

  // Refresh the cost ballpark whenever anything that feeds it changes.
  useEffect(() => {
    if (!selected) return;
    getEstimate(selected, configs).then(setEst).catch(() => setEst(null));
  }, [selected, configs, gold, datasets]);

  const pushLog = (line) => setLog((l) => [...l.slice(-400), line]);

  const doPrepare = async () => {
    setBusy("prepare");
    try {
      await prepareDataset(selected, cap);
      await refresh();
      pushLog(`✓ prepared at ${cap.toLocaleString()} tokens`);
    } catch (e) {
      pushLog(`✗ prepare failed: ${e.message}`);
    } finally { setBusy(""); }
  };

  const doDraft = async (total) => {
    setBusy("gold");
    try {
      await goldgenStream(selected, total, (ev) => {
        if (ev.phase === "progress") pushLog(`drafting questions… ${ev.drafted} drafted (${ev.call}/${ev.calls} calls)`);
        if (ev.phase === "error") pushLog(`✗ ${ev.detail}`);
      });
      const r = await getGold(selected);
      setGold(r.questions);
      setGoldDirty(false);
    } finally { setBusy(""); await refresh(); }
  };

  const doVerify = async () => {
    if (goldDirty) await saveGoldNow();
    setBusy("verify");
    try {
      await goldverifyStream(selected, (ev) => {
        if (ev.phase === "progress") pushLog(`verifying gold… ${ev.i}/${ev.total} · ${ev.approved} approved · ${ev.flagged} flagged`);
        if (ev.phase === "done") pushLog(`✓ auto-verify: ${ev.approved} approved, ${ev.flagged} flagged for your eyes`);
      });
      const r = await getGold(selected);
      setGold(r.questions);
      setGoldDirty(false);
    } finally { setBusy(""); await refresh(); }
  };

  const editGold = (i, patch) => {
    setGold((g) => g.map((q, j) => (j === i ? { ...q, ...patch } : q)));
    setGoldDirty(true);
  };

  const saveGoldNow = async (next = gold) => {
    await putGold(selected, next);
    setGoldDirty(false);
    await refresh();
  };

  const approveAll = async () => {
    const next = gold.map((q) => ({ ...q, status: "approved" }));
    setGold(next);
    await saveGoldNow(next);
  };

  const doRun = async () => {
    if (est?.ready && !est.build_exists) {
      const ok = window.confirm(
        est.build_partial
          ? `Resume the paused build: RAG ${est.rag_done}/${est.rag_total} docs, graph ${est.resumable_episodes}/${est.expected_episodes} episodes already done.\n` +
            `Remaining: ~$${est.build_usd}, ~${est.build_minutes} min, then queries ~$${est.queries_usd}.\n\nContinue?`
          : `This run will BUILD the indexes once (~$${est.build_usd}, ~${est.build_minutes} min, extractor ${est.extract_model}).\n` +
            `Queries on top: ~$${est.queries_usd}.\n\nContinue?`,
      );
      if (!ok) return;
    }
    if (goldDirty) await saveGoldNow();
    setBusy("run");
    setReport(null);
    setLog([]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await runStream({ dataset: selected, configs, signal: controller.signal }, (ev) => {
        if (ev.phase === "start") pushLog(`run ${ev.run_id} · ${ev.questions} questions · build ${ev.fingerprint} → ${ev.save_name}`);
        if (ev.phase === "build_skip") pushLog(`build already exists (${ev.save_name}) — skipping straight to queries ✓`);
        if (ev.phase === "build_adopted") pushLog(`✓ ${ev.detail}`);
        if (ev.phase === "build_resume") pushLog(`↻ ${ev.detail}`);
        if (ev.phase === "build_start") pushLog(`building indexes once… extractor: ${ev.extract_model}`);
        if (ev.phase === "rag_doc") pushLog(ev.skipped ? `vector base · doc ${ev.i}/${ev.total} — already done ✓` : `vector base · doc ${ev.i}/${ev.total} (${ev.chunks} chunks)`);
        if (ev.phase === "graph_episode") pushLog(`graph · doc ${ev.doc_i}/${ev.docs} · episode ${ev.episode}/${ev.episodes}`);
        if (ev.phase === "build_done") pushLog(`✓ built: ${ev.nodes} nodes · ${ev.edges} edges · ${ev.chunks} chunks · saved as a graph-page save (${ev.save_name}) · ${ev.build_seconds}s`);
        if (ev.phase === "config_start") pushLog(`— ${CONFIG_LABELS[ev.config] || ev.config} —`);
        if (ev.phase === "scored") pushLog(`${ev.config} · q${ev.i}/${ev.total} ${ev.judge_correct === true ? "✓" : ev.judge_correct === false ? "✗" : "·"} (F1 ${ev.f1})`);
        if (ev.phase === "report") setReport(ev.report);
        if (ev.phase === "error") pushLog(`✗ ${ev.detail}`);
        if (ev.phase === "done") pushLog("✓ done");
      });
      const r = await listRuns(selected);
      setRuns(r.runs);
      await refresh();
    } catch (e) {
      if (e.name === "AbortError") {
        pushLog("⏸ paused — everything ingested so far is preserved. Press ▶ Continue to resume from here.");
      } else {
        pushLog(`✗ run failed: ${e.message}`);
      }
    } finally { setBusy(""); abortRef.current = null; }
  };

  const doStop = () => abortRef.current?.abort();

  const doDownload = async (urlOverride) => {
    const url = (urlOverride || dlUrl).trim();
    if (!url) return;
    setBusy("download");
    setDlStatus("starting…");
    setDlChoices([]);
    try {
      await downloadStream(url, (ev) => {
        if (ev.phase === "choices") {
          setDlStatus("this repo has several files — pick one:");
          setDlChoices(ev.files);
        }
        if (ev.phase === "download_start") setDlStatus(`downloading ${ev.file}…`);
        if (ev.phase === "progress") setDlStatus(`${ev.mb} MB${ev.total_mb ? ` / ${ev.total_mb} MB` : ""}…`);
        if (ev.phase === "done") { setDlStatus(`✓ added: ${ev.files.join(", ")}`); setDlUrl(""); }
        if (ev.phase === "error") setDlStatus(`✗ ${ev.detail}`);
      });
      await refresh();
    } catch (e) {
      setDlStatus(`✗ ${e.message}`);
    } finally { setBusy(""); }
  };

  const doDeleteDataset = async (name) => {
    const ok = window.confirm(
      `Delete dataset "${name}"?\n\nRemoves the raw file, prepared corpus, gold questions, and run reports.\n` +
      `Graph saves built from it are NOT deleted (manage those on the graph page).`,
    );
    if (!ok) return;
    await deleteDataset(name);
    if (selected === name) setSelected(null);
    await refresh(false);
  };

  const openRun = async (runId) => {
    setReport(await getReport(selected, runId));
  };

  const approved = gold.filter((q) => q.status === "approved").length;
  const humanGold = !!ds?.prepared?.gold_source?.startsWith("human");

  return (
    <div style={page}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 26px", borderBottom: "1px solid rgba(120,135,175,0.14)", position: "sticky", top: 0, background: "rgba(7,9,18,0.85)", backdropFilter: "blur(12px)", zIndex: 10 }}>
        <span style={{ fontSize: 16, fontWeight: 700, color: "#5cc8ff" }}>
          ◇ Noema Bench
        </span>
        <span style={{ fontSize: 11.5, color: "#7a87a6" }}>build once · query per config · fixed report</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <a href="/?view=graph" target="_blank" rel="noreferrer" style={{ ...ghostBtn, textDecoration: "none" }}>◆ Graph</a>
          <a href="/" target="_blank" rel="noreferrer" style={{ ...ghostBtn, textDecoration: "none" }}>✦ Chat</a>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, padding: "18px 26px 40px", maxWidth: 1240, margin: "0 auto" }}>
        {/* datasets rail */}
        <div style={{ width: 250, flexShrink: 0 }}>
          <div style={{ ...label, margin: "4px 0 8px" }}>Datasets</div>
          {datasets === null && <div style={{ color: "#7a87a6", fontSize: 12 }}>loading…</div>}
          {datasets?.length === 0 && (
            <div style={{ ...card, fontSize: 12, color: "#cdd5ea", lineHeight: 1.6 }}>
              No datasets yet. Drop <code>*.jsonl</code> files (one JSON per line with a{" "}
              <code>context</code> field) into
              <div style={{ color: "#8fd6c2", wordBreak: "break-all", marginTop: 6 }}>{rawDir}</div>
            </div>
          )}
          {datasets?.map((d) => (
            <div
              key={d.name}
              onClick={() => setSelected(d.name)}
              style={{
                ...card, padding: 12, marginBottom: 8, cursor: "pointer",
                border: d.name === selected ? "1px solid rgba(92,200,255,0.5)" : card.border,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 650, fontSize: 13.5 }}>{d.name}</span>
                <span style={{ marginLeft: "auto", fontSize: 10.5, color: "#7a87a6" }}>{d.size_mb} MB</span>
                <button
                  title="Delete this dataset (raw file + prepared corpus + gold + reports)"
                  onClick={(e) => { e.stopPropagation(); doDeleteDataset(d.name); }}
                  style={{ background: "none", border: "none", color: "#7a87a6", cursor: "pointer", fontSize: 12, padding: "0 2px" }}
                >
                  ✕
                </button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                <Chip text={d.prepared ? `${(d.prepared.tokens / 1000).toFixed(0)}k tok · ${d.prepared.docs} docs` : "raw"} color={d.prepared ? "#8fd6c2" : "#7a87a6"} />
                {d.prepared?.gold_source?.startsWith("human") && <Chip text="human gold" color="#8fd6c2" />}
                <Chip text={`${d.gold_approved}/${d.gold_total} gold`} color={d.gold_approved ? "#5cc8ff" : "#7a87a6"} />
                {d.builds.length > 0 && <Chip text={`${d.builds.length} build${d.builds.length > 1 ? "s" : ""}`} color="#9b8cff" />}
              </div>
            </div>
          ))}
          <button style={{ ...ghostBtn, width: "100%", marginTop: 4 }} onClick={() => refresh()}>↻ rescan</button>

          <div style={{ ...card, padding: 12, marginTop: 10 }}>
            <div style={{ ...label, marginBottom: 6 }}>Add from URL</div>
            <input
              value={dlUrl}
              onChange={(e) => setDlUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doDownload()}
              placeholder="paste a .json / .jsonl / .tgz link (Hugging Face ok)"
              style={{ ...input, marginBottom: 6 }}
              disabled={busy === "download"}
            />
            <button style={{ ...ghostBtn, width: "100%" }} onClick={() => doDownload()}
              disabled={!dlUrl.trim() || busy === "download"}>
              {busy === "download" ? <span style={spinner} /> : "⇩ Download"}
            </button>
            {dlStatus && <div style={{ fontSize: 11, color: "#8fd6c2", marginTop: 6 }}>{dlStatus}</div>}
            {dlChoices.map((f) => (
              <button key={f.url} onClick={() => doDownload(f.url)}
                style={{ ...ghostBtn, width: "100%", marginTop: 5, textAlign: "left", fontSize: 11.5 }}>
                {f.name} <span style={{ color: "#7a87a6" }}>· {f.mb} MB</span>
              </button>
            ))}
          </div>
        </div>

        {/* workflow column */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {!ds ? (
            <div style={{ ...card, color: "#7a87a6", fontSize: 13 }}>Select a dataset.</div>
          ) : (
            <>
              <Section n="1" title="Prepare the corpus" right={ds.prepared && <Chip text={`hash ${ds.prepared.corpus_hash}`} color="#8fd6c2" />}>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <div style={{ width: 170 }}>
                    <div style={{ ...label, marginBottom: 4 }}>Token cap</div>
                    <input type="number" step={10000} min={10000} value={cap}
                      onChange={(e) => setCap(Number(e.target.value) || 100000)} style={input} disabled={busy !== ""} />
                  </div>
                  <button style={{ ...primaryBtn, width: 150, marginTop: 16 }} onClick={doPrepare} disabled={busy !== ""}>
                    {busy === "prepare" ? <span style={spinner} /> : ds.prepared ? "Re-prepare" : "Prepare"}
                  </button>
                  {ds.prepared && (
                    <span style={{ fontSize: 12, color: "#cdd5ea", marginTop: 14 }}>
                      {ds.prepared.docs} docs · {ds.prepared.tokens.toLocaleString()} tokens
                      <span style={{ color: "#7a87a6" }}> (of {ds.prepared.unique_contexts_in_file} contexts in the file)</span>
                    </span>
                  )}
                </div>
                {ds.prepared && ds.prepared.cap_tokens !== cap && (
                  <div style={{ fontSize: 11.5, color: "#e8c98a", marginTop: 8 }}>
                    Changing the cap re-prepares the corpus → a NEW build fingerprint (the old build + its save stay).
                  </div>
                )}
              </Section>

              <Section
                n="2"
                title={`Gold questions (${approved} approved / ${gold.length})`}
                right={
                  humanGold ? (
                    <Chip text="human gold — came with the dataset, pre-approved" color="#8fd6c2" />
                  ) : (
                    <>
                      {goldDirty && <button style={ghostBtn} onClick={() => saveGoldNow()}>Save edits</button>}
                      <button style={{ ...ghostBtn, color: "#8fd6c2", borderColor: "rgba(143,214,194,0.4)" }}
                        onClick={doVerify} disabled={!gold.some((q) => q.status !== "approved") || busy !== ""}
                        title="Checks every draft: evidence must exist verbatim in the doc, then a judge validates question + answer. Passes get approved; failures stay draft with the reason.">
                        {busy === "verify" ? <span style={spinner} /> : "✓ Auto-verify drafts"}
                      </button>
                      <button style={ghostBtn} onClick={approveAll} disabled={!gold.length || busy !== ""}>Approve all</button>
                      <button style={ghostBtn} onClick={() => doDraft(12)} disabled={!ds.prepared || busy !== ""}>
                        {busy === "gold" ? <span style={spinner} /> : "✎ Draft 12 more"}
                      </button>
                    </>
                  )
                }
              >
                {gold.length === 0 ? (
                  <div style={{ fontSize: 12.5, color: "#7a87a6" }}>
                    No questions yet — draft some (the LLM proposes, you edit and approve; only approved questions run).
                  </div>
                ) : (
                  <div style={{ maxHeight: 340, overflowY: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse" }}>
                      <thead><tr><th style={th}>type</th><th style={th}>question / gold answer</th><th style={th}>status</th><th style={th} /></tr></thead>
                      <tbody>
                        {gold.map((q, i) => (
                          <tr key={q.id}>
                            <td style={{ ...td, width: 70 }}><Chip text={q.type} color={TYPE_COLORS[q.type]} /></td>
                            <td style={td}>
                              <input value={q.question} onChange={(e) => editGold(i, { question: e.target.value })}
                                style={{ ...input, marginBottom: 4, fontWeight: 600 }} />
                              <input value={q.answer} onChange={(e) => editGold(i, { answer: e.target.value })}
                                style={{ ...input, color: "#8fd6c2" }} />
                              {q.flag && (
                                <div style={{ fontSize: 11, color: "#e8a3b8", marginTop: 4 }}>⚑ {q.flag}</div>
                              )}
                            </td>
                            <td style={{ ...td, width: 96 }}>
                              <button
                                style={{ ...ghostBtn, padding: "3px 9px", color: q.status === "approved" ? "#8fd6c2" : "#cdd5ea", borderColor: q.status === "approved" ? "rgba(143,214,194,0.5)" : ghostBtn.border }}
                                onClick={() => editGold(i, { status: q.status === "approved" ? "draft" : "approved" })}
                              >
                                {q.status === "approved" ? "✓ approved" : "draft"}
                              </button>
                            </td>
                            <td style={{ ...td, width: 30 }}>
                              <button style={{ ...ghostBtn, padding: "3px 8px", color: "#e8a3b8" }} title="delete"
                                onClick={() => { setGold((g) => g.filter((_, j) => j !== i)); setGoldDirty(true); }}>✕</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section
                n="3"
                title="Run"
                right={ds.builds.length > 0 && <Chip text={`${ds.builds.length} existing build${ds.builds.length > 1 ? "s" : ""} — matching one is reused, never repaid`} color="#9b8cff" />}
              >
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  {CONFIGS.map((c) => {
                    const on = configs.includes(c);
                    return (
                      <button key={c}
                        style={{ ...ghostBtn, color: on ? "#0a0e1a" : "#cdd5ea", fontWeight: 650, background: on ? "#5cc8ff" : ghostBtn.background, border: on ? "1px solid transparent" : ghostBtn.border }}
                        onClick={() => setConfigs((cs) => (on ? cs.filter((x) => x !== c) : [...cs, c]))}
                        disabled={busy !== ""}
                      >
                        {CONFIG_LABELS[c]}
                      </button>
                    );
                  })}
                  {busy === "run" ? (
                    <button
                      style={{ ...primaryBtn, width: 170, marginLeft: "auto", background: "rgba(232,201,138,0.92)" }}
                      onClick={doStop}
                      title="Pause the run. Everything ingested so far stays; Continue resumes from where it left off.">
                      ⏸ Pause
                    </button>
                  ) : (
                    <button style={{ ...primaryBtn, width: 170, marginLeft: "auto" }}
                      onClick={doRun} disabled={busy !== "" || !approved || configs.length === 0}>
                      {est?.build_partial ? "▶ Continue" : "▶ Run"}
                    </button>
                  )}
                </div>
                {est?.ready && (
                  <div style={{ fontSize: 12, color: "#e8c98a", background: "rgba(232,201,138,0.07)", border: "1px solid rgba(232,201,138,0.22)", borderRadius: 9, padding: "8px 12px", marginBottom: 12 }}>
                    {est.build_exists ? (
                      <>build <b>{est.save_name}</b> already exists — nothing to rebuild. Estimated queries: <b>~${est.queries_usd}</b></>
                    ) : est.build_partial ? (
                      <>paused build: <b>RAG {est.rag_done}/{est.rag_total} docs{est.rag_done === est.rag_total ? " ✓ (done)" : ""}</b> · <b>graph {est.resumable_episodes}/{est.expected_episodes} episodes</b> — Continue finishes the rest for <b>~${est.build_usd}</b> (~{est.build_minutes} min) + queries <b>~${est.queries_usd}</b></>
                    ) : (
                      <>estimated cost: build <b>~${est.build_usd}</b> (one-time, ~{est.build_minutes} min, extractor <code>{est.extract_model}</code>) + queries <b>~${est.queries_usd}</b> = <b>~${est.total_usd}</b></>
                    )}
                    {est.judge_free ? " · judging free (Gemini tier)" : " · judging included at chat-model rates"}
                    <span style={{ color: "#7a87a6" }}> · ±2× until the first real build calibrates it</span>
                  </div>
                )}
                {log.length > 0 && (
                  <div ref={logRef} style={{ maxHeight: 190, overflowY: "auto", background: "rgba(7,10,20,0.7)", border: "1px solid rgba(120,135,175,0.15)", borderRadius: 9, padding: "8px 12px", fontFamily: "ui-monospace, monospace", fontSize: 11.5, lineHeight: 1.75, color: "#9fb0d0" }}>
                    {log.map((l, i) => <div key={i}>{l}</div>)}
                  </div>
                )}
              </Section>

              <Section
                n="4"
                title="Report"
                right={
                  runs.length > 0 && (
                    <select style={{ ...selectStyle, width: 220 }} value={report?.run_id || ""} onChange={(e) => e.target.value && openRun(e.target.value)}>
                      <option value="">history: {runs.length} run{runs.length > 1 ? "s" : ""}…</option>
                      {runs.map((r) => <option key={r.run_id} value={r.run_id}>{r.run_id} — {r.configs?.join(", ")}</option>)}
                    </select>
                  )
                }
              >
                {report ? (
                  <ReportView report={report} dataset={selected} busy={busy}
                    onRejudge={async () => {
                      setBusy("rejudge");
                      try {
                        await rejudgeStream(selected, report.run_id, (ev) => {
                          if (ev.phase === "scored") pushLog(`re-judging · ${ev.i}/${ev.total} ${ev.judge_correct === true ? "✓" : ev.judge_correct === false ? "✗" : "·"}`);
                          if (ev.phase === "report") setReport(ev.report);
                          if (ev.phase === "error") pushLog(`✗ ${ev.detail}`);
                        });
                        const r = await listRuns(selected);
                        setRuns(r.runs);
                      } finally { setBusy(""); }
                    }} />
                ) : (
                  <div style={{ fontSize: 12.5, color: "#7a87a6" }}>
                    Run the bench (or open a past run) to see the report. The built graph appears in the
                    Graph page's <b>⧉ Saves</b> — restore it there to fly around it or Dream on a copy.
                  </div>
                )}
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
