import { useEffect, useRef, useState } from "react";

import {
  attachJobStream,
  deleteDataset,
  deleteRun,
  killRun,
  downloadStream,
  rejudgeStream,
  getActiveJob,
  getEstimate,
  getGold,
  getReport,
  listAllJobs,
  goldgenStream,
  goldverifyStream,
  listDatasets,
  listRuns,
  prepareDataset,
  putGold,
  downloadReportMd,
  runStream,
  stopJob,
} from "../api/bench.js";
import { getSession } from "../api/client.js";
import { fetchModels } from "../api/models.js";
import { ghostBtn, primaryBtn, selectStyle, spinner } from "../graph/styles.js";

const CONFIGS = ["closed_book", "rag", "graph", "hybrid", "lightrag", "lightrag_hybrid"];
const CONFIG_LABELS = {
  closed_book: "Closed-book",
  rag: "Contextual RAG",
  graph: "Graph",
  hybrid: "Hybrid (product)",
  lightrag: "LightRAG",
  lightrag_hybrid: "LightRAG hybrid",
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
const th = { textAlign: "left", padding: "6px 10px", color: "#7a87a6", fontSize: 10.5, letterSpacing: 0.8, textTransform: "uppercase", borderBottom: "1px solid rgba(120,135,175,0.14)" };
const td = { padding: "7px 10px", fontSize: 12.5, borderBottom: "1px solid rgba(120,135,175,0.14)", verticalAlign: "top" };

const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function Chip({ text, color = "#7a87a6" }) {
  return (
    <span style={{ fontSize: 10, fontWeight: 600, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`, background: `color-mix(in srgb, ${color} 12%, transparent)`, borderRadius: 6, padding: "1.5px 7px", whiteSpace: "nowrap" }}>
      {text}
    </span>
  );
}

function ProgressRing({ pct, size = 15 }) {
  const r = (size - 3) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)", flexShrink: 0 }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(143,214,194,0.22)" strokeWidth="2.5" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#8fd6c2" strokeWidth="2.5"
        strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(1, pct))} strokeLinecap="round" />
    </svg>
  );
}

function fmtEta(s) {
  if (s == null) return "estimating…";
  if (s < 90) return "~1 min left";
  const m = Math.round(s / 60);
  if (m < 90) return `~${m} min left`;
  return `~${Math.floor(m / 60)}h${String(m % 60).padStart(2, "0")} left`;
}

function Section({ n, title, children, right }) {
  return (
    <div style={{ ...card, marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <span style={{ width: 22, height: 22, borderRadius: 7, display: "grid", placeItems: "center", fontSize: 11.5, fontWeight: 700, color: "#ffffff", background: "#3f6fe0" }}>{n}</span>
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
            {["config", "n", "judge acc", "lift", "EM", "F1", "evidence", "ev source", "latency", "tok/q"].map((h) => (
              <th key={h} style={th}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.config} style={r.config === "hybrid" ? { background: "rgba(155,140,255,0.06)" } : undefined}>
              <td style={{ ...td, fontWeight: 650 }}>{CONFIG_LABELS[r.config] || r.config}</td>
              <td style={td}>{r.n}</td>
              <td style={{ ...td, color: "#5cc8ff", fontWeight: 650 }}>
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
              <td style={td} title="Evidence source recall — how often a retrieved fact's provenance window is where the gold evidence lives (the fair evidence signal for fact stores)">
                {pct(r.evidence_source_recall)}
              </td>
              <td style={td}>{r.latency_ms_avg} ms</td>
              <td style={td}>{r.tokens_per_q}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReportView({ report, dataset, onRejudge, onDelete, busy }) {
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
        <button
          style={ghostBtn}
          title="Download this run's report.md"
          onClick={() =>
            downloadReportMd(dataset, report.run_id).catch((e) => alert(e.message))
          }
        >
          ⬇ report.md
        </button>
        <button
          style={{ ...ghostBtn, color: "#e8a3b8", borderColor: "rgba(232,163,184,0.35)" }}
          title="Delete this run's report from the workdir. The copy in bench_archive/ on this machine is kept."
          onClick={onDelete}
          disabled={busy !== ""}
        >
          🗑 Delete
        </button>
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
      {report.provenance?.reasoning_efforts && (
        <div style={{ fontSize: 11.5, color: "#7a87a6", marginTop: 4 }}>
          effort — extraction: <b style={{ color: "#9aa6c2" }}>{report.provenance.reasoning_efforts.extract}</b>
          {" · "}contextualizer: <b style={{ color: "#9aa6c2" }}>{report.provenance.reasoning_efforts.context}</b>
          {" · "}answers: <b style={{ color: "#9aa6c2" }}>{report.provenance.reasoning_efforts.answer}</b>
          {" · "}judge: <b style={{ color: "#9aa6c2" }}>{report.provenance.reasoning_efforts.judge}</b>
        </div>
      )}
      {(report.model_usage || []).length > 0 && (
        <div style={{ fontSize: 11.5, color: "#7a87a6", marginTop: 4 }}>
          {report.model_usage.map((m) => (
            <span key={`${m.role}:${m.model}`} style={{ marginRight: 16 }}>
              {m.role}: <b style={{ color: "#9aa6c2" }}>{m.model}</b>
              {m.prompt_tokens != null && (
                <> — {m.prompt_tokens.toLocaleString()} in / {(m.completion_tokens ?? 0).toLocaleString()} out</>
              )}
            </span>
          ))}
        </div>
      )}

      {Object.keys(report.slices || {}).length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ ...label, marginBottom: 6 }}>By question type</div>
          {Object.entries(report.slices).map(([qtype, rows]) => (
            <div key={qtype} style={{ fontSize: 12, color: "#e7ecf7", marginBottom: 3 }}>
              <Chip text={qtype} color={TYPE_COLORS[qtype]} />{" "}
              {rows.map((r) => `${CONFIG_LABELS[r.config] || r.config} ${pct(r.judge_accuracy)}`).join(" · ")}
            </div>
          ))}
        </div>
      )}

      {[["Fusion (hybrid vs rag)", fusion], ["Fusion (LightRAG hybrid vs rag)", report.fusion_lightrag]].map(
        ([title, f]) =>
          f && (
            <div key={title} style={{ marginTop: 14, fontSize: 12.5, color: "#e7ecf7" }}>
              <div style={{ ...label, marginBottom: 6 }}>{title}</div>
              supplement share of context {pct(f.graph_share_of_context)}
              {f.paired_questions != null && (
                <>
                  {" "}· paired on {f.paired_questions} questions: fixed{" "}
                  <b style={{ color: "#8fd6c2" }}>{f.hybrid_gained_over_rag}</b> / broke{" "}
                  <b style={{ color: "#e8a3b8" }}>{f.hybrid_lost_vs_rag}</b>
                  {f.mcnemar_p != null && ` · McNemar p=${f.mcnemar_p}`}
                </>
              )}
            </div>
          ),
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
              <div style={{ color: "#e7ecf7" }}>got: {f.answer || `(error: ${f.error})`}</div>
              {f.note && <div style={{ color: "#7a87a6" }}>judge: {f.note}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BenchPage() {
  // Bench builds and runs spend real money — the backend serves it to admins only
  // (403 otherwise); this gate just explains that instead of showing dead controls.
  if (!getSession()?.isAdmin) return <AdminOnlyNotice />;
  return <Bench />;
}

function AdminOnlyNotice() {
  return (
    <div style={{ ...page, display: "grid", placeItems: "center" }}>
      <div style={{ ...card, maxWidth: 420, textAlign: "center", padding: 28 }}>
        <div style={{ fontSize: 17, fontWeight: 600, marginBottom: 8 }}>Admin only</div>
        <div style={{ fontSize: 13, color: "#9aa6c2", lineHeight: 1.6 }}>
          The bench launches paid builds and runs, so it is limited to admin
          accounts. Ask an admin to grant you access, or sign in with the admin
          account and reopen this tab.
        </div>
        <a
          href={`${window.location.origin}/`}
          style={{ ...ghostBtn, display: "inline-block", marginTop: 16, textDecoration: "none" }}
        >
          Open chat ↗
        </a>
      </div>
    </div>
  );
}

function Bench() {
  const [datasets, setDatasets] = useState(null);
  const [rawDir, setRawDir] = useState("");
  const [selected, setSelected] = useState(null);
  const [cap, setCap] = useState(100000);
  const [gold, setGold] = useState([]);
  const [goldDirty, setGoldDirty] = useState(false);
  const [configs, setConfigs] = useState(["closed_book", "rag", "graph", "hybrid"]);
  const [scope, setScope] = useState("auto"); // "auto" = follow the dataset (scope to each question's source doc when it has one)
  // Per-run model picks, one per role; "" = the role's default. Extractor and
  // contextualizer land in the build fingerprint (a new pick = a new build).
  const [models, setModels] = useState({ extract: "", context: "", answer: "", judge: "" });
  const [modelList, setModelList] = useState([]);
  const [defaults, setDefaults] = useState({ chat: "", strong: "", judge: "", efforts: {} });
  // Per-run reasoning-effort overrides; "" = the research-backed env default.
  const [efforts, setEfforts] = useState({ extract: "", context: "", answer: "", judge: "" });
  const [activeJobs, setActiveJobs] = useState([]); // every dataset's running job (overnight view)
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
  const jobRef = useRef(null); // the detached server job we're tailing

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
    fetchModels()
      .then((r) => { setModelList(r.models); setDefaults({ chat: r.default, strong: r.strong, judge: r.judge, efforts: r.efforts || {} }); })
      .catch(() => {});
  }, []);

  // The overnight view: poll every running job across datasets, so launching
  // several and sleeping still shows everything spinning in the header.
  useEffect(() => {
    const load = () => listAllJobs().then((r) => setActiveJobs(r.jobs || [])).catch(() => {});
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!selected) return;
    // Switching datasets drops the current TAIL only — the server job keeps
    // running (that's the point of detached jobs) and this same effect
    // reattaches when you come back. This is what lets several datasets run
    // at once from one tab: Run A, switch, Run B, sleep.
    abortRef.current?.abort();
    abortRef.current = null;
    jobRef.current = null;
    setBusy("");
    setReport(null);
    setLog([]);
    getGold(selected).then((r) => { setGold(r.questions); setGoldDirty(false); }).catch(() => setGold([]));
    listRuns(selected).then((r) => setRuns(r.runs)).catch(() => setRuns([]));
    const prepared = datasets?.find((d) => d.name === selected)?.prepared;
    if (prepared?.cap_tokens) setCap(prepared.cap_tokens);
    // A run outlives its tab (detached server job) — if one is still going for this
    // dataset, reattach and replay its full log instead of leaving it invisible.
    getActiveJob(selected).then(({ job }) => {
      if (!job || job.done || abortRef.current) return;
      setBusy("run");
      pushLog(`↻ a ${job.kind} started at ${job.started_at} is still going on the server — reattaching…`);
      const controller = new AbortController();
      abortRef.current = controller;
      jobRef.current = job.job_id;
      attachJobStream(job.job_id, 0, handleRunEvent, controller.signal)
        .then(async () => {
          const r = await listRuns(selected);
          setRuns(r.runs);
          await refresh();
        })
        .catch(() => {})
        .finally(() => {
          // Only clean up if WE are still the attached tail — a dataset switch
          // may already have handed the refs to another attachment.
          if (abortRef.current === controller) {
            setBusy(""); abortRef.current = null; jobRef.current = null;
          }
        });
    }).catch(() => {});
  }, [selected]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [log]);

  // Refresh the cost ballpark whenever anything that feeds it changes.
  useEffect(() => {
    if (!selected) return;
    getEstimate(selected, configs, models).then(setEst).catch(() => setEst(null));
  }, [selected, configs, gold, datasets, models]);

  const pushLog = (line) => setLog((l) => [...l.slice(-400), line]);

  // One narrator for run events, shared by a fresh run and a reattached one.
  const handleRunEvent = (ev) => {
    if (ev.phase === "job") jobRef.current = ev.job_id;
    if (ev.phase === "start") {
      pushLog(`run ${ev.run_id} · ${ev.questions} questions · scope: ${ev.scope || "doc"} · build ${ev.fingerprint} → ${ev.save_name}`);
      if (ev.efforts) pushLog(`efforts — extract: ${ev.efforts.extract} · context: ${ev.efforts.context} · answer: ${ev.efforts.answer} · judge: ${ev.efforts.judge}`);
    }
    if (ev.phase === "build_skip") pushLog(`build already exists (${ev.save_name}) — skipping straight to queries ✓`);
    if (ev.phase === "build_adopted") pushLog(`✓ ${ev.detail}`);
    if (ev.phase === "build_resume") pushLog(`↻ ${ev.detail}`);
    if (ev.phase === "build_start") pushLog(`building indexes once… extractor: ${ev.extract_model}`);
    if (ev.phase === "rag_doc") pushLog(ev.skipped ? `vector base · doc ${ev.i}/${ev.total} — already done ✓` : `vector base · doc ${ev.i}/${ev.total} (${ev.chunks} chunks)`);
    if (ev.phase === "graph_episode") pushLog(`graph · doc ${ev.doc_i}/${ev.docs} · episode ${ev.episode}/${ev.episodes}`);
    if (ev.phase === "build_done") pushLog(`✓ built: ${ev.nodes} nodes · ${ev.edges} edges · ${ev.chunks} chunks · saved as a graph-page save (${ev.save_name}) · ${ev.build_seconds}s`);
    if (ev.phase === "lightrag_build_skip") pushLog(`LightRAG build already exists (${ev.save_name}) ✓`);
    if (ev.phase === "lightrag_build_reset") pushLog(`↻ ${ev.detail}`);
    if (ev.phase === "lightrag_build_start") pushLog(`building the LightRAG leg… (${ev.resumed_docs}/${ev.docs} docs already done)`);
    if (ev.phase === "lightrag_doc") pushLog(ev.skipped ? `LightRAG · doc ${ev.i}/${ev.total} — already done ✓` : `LightRAG · doc ${ev.i}/${ev.total} (${ev.pieces} pieces)`);
    if (ev.phase === "lightrag_build_done") pushLog(`✓ LightRAG leg built (${ev.save_name}) · ${ev.build_seconds}s`);
    if (ev.phase === "answers_reused") pushLog(`♻ ${ev.detail}`);
    if (ev.phase === "query_resume") pushLog(`↻ ${ev.detail}`);
    if (ev.phase === "config_start") pushLog(`— ${CONFIG_LABELS[ev.config] || ev.config} —`);
    if (ev.phase === "answered") pushLog(ev.resumed ? `${ev.config} · q${ev.i}/${ev.total} — already answered ✓` : ev.error ? `${ev.config} · q${ev.i}/${ev.total} ✗ infra error (excluded, will retry on resume)` : `${ev.config} · q${ev.i}/${ev.total} answered (F1 ${ev.f1})`);
    if (ev.phase === "judge_start") pushLog(`— judging ${ev.verdicts} answers (${ev.concurrency} in parallel) —`);
    if (ev.phase === "scored") pushLog(`judge · ${ev.i}/${ev.total} ${ev.config} ${ev.judge_correct === true ? "✓" : ev.judge_correct === false ? "✗" : "·"} (F1 ${ev.f1})`);
    if (ev.phase === "report") setReport(ev.report);
    if (ev.phase === "results_archived") pushLog(`⛃ ${ev.detail}`);
    if (ev.phase === "results_archive_error") pushLog(`⚠ archive: ${ev.detail}`);
    if (ev.phase === "stopped") pushLog(`⏸ ${ev.detail}`);
    if (ev.phase === "error") pushLog(`✗ ${ev.detail}`);
    if (ev.phase === "done") pushLog("✓ done");
  };

  const doPrepare = async () => {
    setBusy("prepare");
    try {
      await prepareDataset(selected, cap);
      await refresh();
      const r = await getGold(selected).catch(() => ({ questions: [] }));
      setGold(r.questions);
      setGoldDirty(false);
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
    if (!est?.ready) {
      // The cost gate must never silently vanish just because the estimate failed to load.
      const ok = window.confirm(
        "Cost estimate is unavailable right now, so this run could build indexes and spend " +
        "money without a number shown first.\n\nStart the run anyway?",
      );
      if (!ok) return;
    } else if (!est.build_exists) {
      const unpriced = est.unpriced_models?.length
        ? `\n⚠ ${est.unpriced_models.join(", ")} not in the price table — priced at mini-tier, treat the build figure as a floor.`
        : "";
      const ok = window.confirm(
        (est.build_partial
          ? `Resume the paused build: RAG ${est.rag_done}/${est.rag_total} docs, graph ${est.resumable_episodes}/${est.expected_episodes} episodes already done.\n` +
            `Remaining: ~$${est.build_usd}, ~${est.build_minutes} min, then queries ~$${est.queries_usd}.`
          : `This run will BUILD the indexes once (~$${est.build_usd}, ~${est.build_minutes} min, extractor ${est.extract_model}).\n` +
            `Queries on top: ~$${est.queries_usd}${est.judge_minutes ? `, ~${est.judge_minutes} min of judging` : ""}.`) +
        unpriced + `\n\nContinue?`,
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
      await runStream({
        dataset: selected, configs, scope,
        extractModel: models.extract, answerModel: models.answer,
        judgeModel: models.judge, contextModel: models.context,
        efforts,
        signal: controller.signal,
      }, handleRunEvent);
      const r = await listRuns(selected);
      setRuns(r.runs);
      await refresh();
    } catch (e) {
      if (e.name !== "AbortError") pushLog(`✗ run failed: ${e.message}`);
    } finally {
      if (abortRef.current === controller) {
        setBusy(""); abortRef.current = null; jobRef.current = null;
      }
    }
  };

  // Pause = stop the SERVER job (aborting our tail alone would leave it running,
  // which is exactly what we want on tab close — but Pause means pause).
  const doStop = async () => {
    if (jobRef.current) await stopJob(jobRef.current).catch(() => {});
    abortRef.current?.abort();
    pushLog("⏸ pause requested — everything built, answered and judged so far is saved. Press ▶ Continue to resume.");
  };

  const doKill = async () => {
    if (!window.confirm(`Kill the ${selected} run and discard its partial answers? The next Run starts from question 1. Builds and finished reports are kept.`)) return;
    abortRef.current?.abort();
    try {
      const r = await killRun(selected);
      pushLog(`✖ killed — ${r.discarded_partials} partial answer log${r.discarded_partials === 1 ? "" : "s"} discarded. Next Run starts from the beginning.`);
    } catch (e) { pushLog(`✗ ${e.message}`); }
  };

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
  const humanGold = !!ds?.human_gold || !!ds?.prepared?.gold_source?.startsWith("human");

  return (
    <div style={page}>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.45;transform:scale(0.75)}}`}</style>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 26px", borderBottom: "1px solid rgba(120,135,175,0.14)", position: "sticky", top: 0, background: "rgba(13,18,32,0.92)", backdropFilter: "blur(12px)", zIndex: 10 }}>
        <span style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
          <span style={{ color: "#3f6fe0", fontSize: 17 }}>◇</span>
          <span style={{ fontSize: 16.5, fontWeight: 700, letterSpacing: 0.2, color: "#eef2fb" }}>
            Noema <span style={{ color: "#9aa6c2", fontWeight: 500 }}>Bench</span>
          </span>
        </span>
        <span style={{ fontSize: 11.5, color: "#7a87a6", borderLeft: "1px solid rgba(120,135,175,0.25)", paddingLeft: 12 }}>
          build once · query per config · fixed report
        </span>
        {activeJobs.length > 0 && (
          <span style={{ display: "flex", gap: 6, alignItems: "center", marginLeft: 6 }}>
            {activeJobs.map((j) => (
              <button
                key={j.job_id}
                onClick={() => setSelected(j.dataset)}
                title={`${j.kind} started ${j.started_at} — click to watch (runs keep going server-side while you look elsewhere)`}
                style={{ ...ghostBtn, padding: "3px 10px", fontSize: 11, color: "#8fd6c2", borderColor: "rgba(143,214,194,0.4)", display: "flex", alignItems: "center", gap: 6 }}
              >
                <span style={{ ...spinner, width: 9, height: 9 }} />
                {j.dataset}
              </button>
            ))}
          </span>
        )}
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
            <div style={{ ...card, fontSize: 12, color: "#e7ecf7", lineHeight: 1.6 }}>
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
                border: d.name === selected ? "1px solid rgba(92,200,255,0.25)" : card.border,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 650, fontSize: 13.5 }}>{d.name}</span>
                {(() => {
                  const job = activeJobs.find((j) => j.dataset === d.name);
                  if (!job) return null;
                  const pr = job.progress || {};
                  return (
                    <span
                      title={`${pr.stage || "running"} ${pr.total ? `${pr.done}/${pr.total}` : ""} — keeps going server-side even if you close the tab`}
                      style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, color: "#8fd6c2" }}
                    >
                      <ProgressRing pct={pr.pct || 0} />
                      {Math.round((pr.pct || 0) * 100)}%
                      <span style={{ color: "#7a87a6", fontWeight: 500 }}>{fmtEta(pr.eta_seconds)}</span>
                    </span>
                  );
                })()}
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
                {(d.human_gold || d.prepared?.gold_source?.startsWith("human")) && <Chip text="human gold" color="#8fd6c2" />}
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
              {ds.about && (
                <div style={{ ...card, fontSize: 12.5, color: "#e7ecf7", lineHeight: 1.6, marginBottom: 12 }}>
                  <div style={{ ...label, marginBottom: 5 }}>About this dataset</div>
                  {ds.about}
                </div>
              )}
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
                    <span style={{ fontSize: 12, color: "#e7ecf7", marginTop: 14 }}>
                      {ds.prepared.docs} docs · {ds.prepared.tokens.toLocaleString()} tokens
                      <span style={{ color: "#7a87a6" }}> (of {ds.prepared.unique_contexts_in_file} contexts in the file)</span>
                      {ds.prepared.questions_kept != null && (
                        <span style={{ color: "#8fd6c2" }}
                          title="A question is only kept when EVERY document it needs fits under the cap — no question ever runs without its context in the corpus.">
                          {" "}· {ds.prepared.questions_kept} of {ds.prepared.questions_in_file} questions kept, each with all its documents
                        </span>
                      )}
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
                    {humanGold
                      ? "This dataset ships its own human questions — prepare the corpus above and they appear here, pre-approved (no LLM involved)."
                      : "No questions yet — draft some (the LLM proposes, you edit and approve; only approved questions run)."}
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
                                style={{ ...ghostBtn, padding: "3px 9px", color: q.status === "approved" ? "#8fd6c2" : "#e7ecf7", borderColor: q.status === "approved" ? "rgba(143,214,194,0.5)" : ghostBtn.border }}
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
                right={ds.builds.length > 0 && (
                  <span
                    title="Existing builds and the models that created them — a run whose picks match one reuses it, never repaid"
                    style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}
                  >
                    {ds.builds.slice(-3).map((b) => (
                      <Chip
                        key={b.fingerprint}
                        color="#9b8cff"
                        text={`${b.fingerprint?.slice(0, 6)} · ${b.models?.extract || "?"}${b.models?.context ? ` +ctx ${b.models.context}` : ""}`}
                      />
                    ))}
                    {ds.builds.length > 3 && <Chip text={`+${ds.builds.length - 3} more`} color="#9b8cff" />}
                  </span>
                )}
              >
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 12 }}>
                  {[
                    ["extract", "graph creator (extractor)", defaults.strong || "strong model",
                     "Builds the knowledge graph (and the LightRAG leg). Defaults to the STRONG model — extraction quality caps every graph config. Part of the build fingerprint: a different pick = a NEW build (paid)."],
                    ["context", "contextualizer", defaults.chat || "chat model",
                     "Writes the situating blurb per chunk (RAG build). Part of the build fingerprint: a different pick = a NEW build (paid)."],
                    ["answer", "answerer", defaults.chat || "chat model",
                     "Generates every config's answers — identical across configs by design."],
                    ["judge", "judge", defaults.judge || "judge model",
                     "Scores answers against the gold. Uses the JUDGE_* endpoint when configured, else the main provider. Changing ONLY the judge re-uses a finished run's answers — verdicts are the only cost."],
                  ].map(([key, title, dflt, hint]) => (
                    <label key={key} title={hint} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <span style={label}>{title}</span>
                      <select
                        value={models[key]}
                        onChange={(e) => setModels((m) => ({ ...m, [key]: e.target.value }))}
                        disabled={busy !== ""}
                        style={{ ...selectStyle, width: 190 }}
                      >
                        <option value="">{dflt}</option>
                        {modelList.map((m) => <option key={m} value={m}>{m}</option>)}
                      </select>
                    </label>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 12 }}>
                  {[
                    ["extract", "extractor effort",
                     "Thinking depth for graph extraction. Part of the build fingerprint: a different pick = a NEW build (paid). Default is research-backed (medium — deeper shows no extraction gain)."],
                    ["context", "contextualizer effort",
                     "Thinking depth for the situating blurbs. Part of the build fingerprint. Default low — summarization-class, deeper buys nothing."],
                    ["answer", "answerer effort",
                     "Thinking depth for every config's answers — identical across configs. Part of the answer identity (changing it re-answers, builds are reused)."],
                    ["judge", "judge effort",
                     "Thinking depth for verdicts. Default high — the one role with measured accuracy gains from effort. Logged in run provenance."],
                  ].map(([key, title, hint]) => (
                    <label key={key} title={hint} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      <span style={label}>{title}</span>
                      <select
                        value={efforts[key]}
                        onChange={(e) => setEfforts((m) => ({ ...m, [key]: e.target.value }))}
                        disabled={busy !== ""}
                        style={{ ...selectStyle, width: 190 }}
                      >
                        <option value="">{defaults.efforts?.[key] || "default"} · default</option>
                        {["none", "low", "medium", "high", "xhigh"].map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  {CONFIGS.map((c) => {
                    const on = configs.includes(c);
                    return (
                      <button key={c}
                        style={{ ...ghostBtn, color: on ? "#ffffff" : "#e7ecf7", fontWeight: 650, background: on ? "#3f6fe0" : ghostBtn.background, border: on ? "1px solid rgba(255,255,255,0.14)" : ghostBtn.border }}
                        onClick={() => setConfigs((cs) => (on ? cs.filter((x) => x !== c) : [...cs, c]))}
                        disabled={busy !== ""}
                      >
                        {CONFIG_LABELS[c]}
                      </button>
                    );
                  })}
                  {busy === "run" ? (
                    <span style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
                      <button
                        style={{ ...primaryBtn, width: 130, background: "rgba(232,201,138,0.12)", border: "1px solid rgba(232,201,138,0.4)", color: "#e8c98a" }}
                        onClick={doStop}
                        title="Pause the server-side run (closing the tab does NOT stop it — it keeps going and the page reattaches on reload). Everything built, answered and judged so far stays; Continue resumes from exactly here.">
                        ⏸ Pause
                      </button>
                      <button
                        style={{ ...primaryBtn, width: 110, background: "rgba(232,163,184,0.12)", border: "1px solid rgba(232,163,184,0.35)", color: "#e8a3b8" }}
                        onClick={doKill}
                        title="Stop AND discard this dataset's partial answers — the next Run starts from question 1. Builds and finished reports are kept (delete a finished report too if you want its answers regenerated).">
                        ✖ Kill
                      </button>
                    </span>
                  ) : (
                    <button style={{ ...primaryBtn, width: 170, marginLeft: "auto" }}
                      onClick={doRun} disabled={busy !== "" || !approved || configs.length === 0}>
                      {est?.build_partial ? "▶ Continue" : "▶ Run"}
                    </button>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
                  <span style={{ fontSize: 11.5, color: "#7a87a6" }}>Retrieval scope</span>
                  {[
                    ["auto", "Auto — from dataset", "Follows the dataset: a question tied to one source document (like QASPER, every question) retrieves only from that document; a corpus-wide dataset searches everything. This is the correct condition — you shouldn't normally change it."],
                    ["corpus", "Force whole corpus", "Override for demonstration only: search all documents at once. For per-document gold (QASPER) this makes questions ambiguous across papers — the failure mode, on purpose."],
                  ].map(([val, label, tip]) => {
                    const on = scope === val;
                    return (
                      <button key={val} title={tip}
                        style={{ ...ghostBtn, fontSize: 11.5, padding: "5px 11px", color: on ? "#ffffff" : "#e7ecf7", fontWeight: 650, background: on ? "#3f6fe0" : ghostBtn.background, border: on ? "1px solid rgba(255,255,255,0.14)" : ghostBtn.border }}
                        onClick={() => setScope(val)} disabled={busy !== ""}>
                        {label}
                      </button>
                    );
                  })}
                  <span style={{ fontSize: 11, color: "#7a87a6" }}>
                    {scope === "auto" ? "each question scoped to its source document, as the dataset defines" : "override: forcing whole-corpus search (demonstrates cross-document ambiguity)"}
                  </span>
                </div>
                {est?.ready && (
                  <div style={{ fontSize: 12, color: "#e8c98a", background: "rgba(232,201,138,0.12)", border: "1px solid rgba(232,201,138,0.4)", borderRadius: 9, padding: "8px 12px", marginBottom: 12 }}>
                    {est.build_exists ? (
                      <>build <b>{est.save_name}</b> already exists{est.build_breakdown?.lightrag_extraction_usd != null ? <> — only the LightRAG leg to build: <b>~${est.build_breakdown.lightrag_extraction_usd}</b></> : <> — nothing to rebuild</>}. Estimated queries: <b>~${est.queries_usd}</b></>
                    ) : est.build_partial ? (
                      <>paused build: <b>RAG {est.rag_done}/{est.rag_total} docs{est.rag_done === est.rag_total ? " ✓ (done)" : ""}</b> · <b>graph {est.resumable_episodes}/{est.expected_episodes} episodes</b> — Continue finishes the rest for <b>~${est.build_usd}</b> (~{est.build_minutes} min) + queries <b>~${est.queries_usd}</b></>
                    ) : (
                      <>estimated cost: build <b>~${est.build_usd}</b> (one-time, ~{est.build_minutes} min, extractor <code>{est.extract_model}</code>) + queries <b>~${est.queries_usd}</b> = <b>~${est.total_usd}</b>
                        {est.build_breakdown?.contextualization_usd != null && (
                          <span style={{ color: "#7a87a6" }}> · build = ${est.build_breakdown.contextualization_usd} contextualize + ${est.build_breakdown.graph_extraction_usd} extract{est.build_breakdown.lightrag_extraction_usd != null && ` + $${est.build_breakdown.lightrag_extraction_usd} LightRAG`}</span>
                        )}</>
                    )}
                    {est.judge_free ? ` · judging free (Gemini tier)${est.judge_minutes ? `, ~${est.judge_minutes} min throttled` : ""}` : " · judging included at chat-model rates"}
                    {est.unpriced_models?.length > 0 && (
                      <span style={{ color: "#e8a3b8" }}> · ⚠ {est.unpriced_models.join(", ")} priced at mini-tier (unknown) — build figure is a floor</span>
                    )}
                    <span style={{ color: "#7a87a6" }}> · graph-extraction term still ±2× until a real build calibrates it</span>
                  </div>
                )}
                {log.length > 0 && (
                  <div ref={logRef} style={{ maxHeight: 190, overflowY: "auto", background: "rgba(7,10,20,0.7)", border: "1px solid rgba(120,135,175,0.14)", borderRadius: 9, padding: "8px 12px", fontFamily: "ui-monospace, monospace", fontSize: 11.5, lineHeight: 1.75, color: "#9aa6c2" }}>
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
                    onDelete={async () => {
                      if (!window.confirm(`Delete run ${report.run_id}? The archive copy on this machine is kept.`)) return;
                      try {
                        await deleteRun(selected, report.run_id);
                        setReport(null);
                        const r = await listRuns(selected);
                        setRuns(r.runs);
                      } catch (e) { pushLog(`✗ ${e.message}`); }
                    }}
                    onRejudge={async () => {
                      setBusy("rejudge");
                      try {
                        await rejudgeStream(selected, report.run_id, models.judge, (ev) => {
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
