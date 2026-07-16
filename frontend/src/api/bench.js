// The bench surface: datasets → prepare → gold questions → run (streamed) → report.
import { API_BASE, asJson, authFetch, readNdjsonStream } from "./client.js";

export const listDatasets = () => authFetch(`${API_BASE}/bench/datasets`).then(asJson);

export const prepareDataset = (dataset, capTokens) =>
  authFetch(`${API_BASE}/bench/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, cap_tokens: capTokens }),
  }).then(asJson);

export const getGold = (dataset) =>
  authFetch(`${API_BASE}/bench/gold?dataset=${encodeURIComponent(dataset)}`).then(asJson);

export const putGold = (dataset, questions) =>
  authFetch(`${API_BASE}/bench/gold`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, questions }),
  }).then(asJson);

// Streams {phase:"start"|"progress"|"done"|"error", ...} while the LLM drafts questions.
export async function goldgenStream(dataset, total, onEvent) {
  const res = await authFetch(`${API_BASE}/bench/goldgen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, total }),
  });
  await readNdjsonStream(res, onEvent);
}

// Streams the auto-verify pass over draft questions: mechanical evidence check +
// one judge call each; passes get approved, failures stay draft with a `flag`.
export async function goldverifyStream(dataset, onEvent) {
  const res = await authFetch(`${API_BASE}/bench/goldverify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset }),
  });
  await readNdjsonStream(res, onEvent);
}

// Streams the whole run: build (or build_skip) → per-question scoring → report.
// `signal` aborts mid-run; everything ingested AND every answered question is persisted,
// so re-running resumes from exactly where it stopped (nothing is re-paid).
export async function runStream({ dataset, configs, extractModel, answerModel, scope, signal }, onEvent) {
  const res = await authFetch(`${API_BASE}/bench/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      dataset,
      configs,
      extract_model: extractModel || null,
      answer_model: answerModel || null,
      scope: scope || "auto",
    }),
    signal,
  });
  await readNdjsonStream(res, onEvent);
}

// Streams a dataset download from a URL into the raw dir:
// {phase:"download_start"|"progress"|"done"|"error", ...}
export async function downloadStream(url, onEvent) {
  const res = await authFetch(`${API_BASE}/bench/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  await readNdjsonStream(res, onEvent);
}

// Re-scores a stored run's answers with the current judge + gold (no generation cost).
export async function rejudgeStream(dataset, runId, onEvent) {
  const res = await authFetch(`${API_BASE}/bench/rejudge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset, run_id: runId }),
  });
  await readNdjsonStream(res, onEvent);
}

export const deleteDataset = (name) =>
  authFetch(`${API_BASE}/bench/delete-dataset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  }).then(asJson);

export const getEstimate = (dataset, configs) =>
  authFetch(
    `${API_BASE}/bench/estimate?dataset=${encodeURIComponent(dataset)}&configs=${configs.join(",")}`,
  ).then(asJson);

export const listRuns = (dataset) =>
  authFetch(`${API_BASE}/bench/runs?dataset=${encodeURIComponent(dataset)}`).then(asJson);

export const getReport = (dataset, runId) =>
  authFetch(
    `${API_BASE}/bench/report?dataset=${encodeURIComponent(dataset)}&run_id=${encodeURIComponent(runId)}`,
  ).then(asJson);

export const reportMdUrl = (dataset, runId) =>
  `${API_BASE}/bench/report.md?dataset=${encodeURIComponent(dataset)}&run_id=${encodeURIComponent(runId)}`;
