// The real graph memory (Graphiti). Extraction is slow, so PDF upload streams
// NDJSON — one event per page — and the page draws the graph as it grows.
import { API_BASE, asJson, authFetch, readNdjsonStream } from "./client.js";

export function getGraph(domain = "default") {
  return authFetch(`${API_BASE}/graphmem?domain=${domain}`).then(asJson);
}

export function ingestText(text, model, source, domain = "default") {
  return authFetch(`${API_BASE}/graphmem/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model, source, domain }),
  }).then(asJson);
}

export function resetGraph(domain = "default") {
  return authFetch(`${API_BASE}/graphmem/reset?domain=${domain}`, { method: "POST" }).then(asJson);
}

// Save / restore checkpoints, scoped per memory engine ("graphiti" | "lightrag");
// an empty engine lists the union of both (the chat selector's view).
export function listSaves(domain = "default", engine = "") {
  return authFetch(`${API_BASE}/graphmem/saves?domain=${domain}&engine=${engine}`).then(asJson);
}

function savePost(path, name, domain, engine) {
  return authFetch(`${API_BASE}/graphmem/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, domain, engine }),
  }).then(asJson);
}

export const saveGraph = (name, engine, domain = "default") => savePost("save", name, domain, engine);
export const restoreGraph = (name, engine, domain = "default") => savePost("restore", name, domain, engine);
export const deleteSave = (name, engine, domain = "default") => savePost("delete-save", name, domain, engine);

// Streams the per-page extraction. `onEvent` is called for each NDJSON line:
// {phase:"parsing"|"parsed"|"page"|"error"|"done", ...}. A "page" event carries a
// fresh {nodes, links, stats} snapshot.
export async function uploadPdfStream(file, model, onEvent, domain = "default") {
  const form = new FormData();
  form.append("file", file);
  if (model) form.append("model", model);
  form.append("domain", domain);
  const res = await authFetch(`${API_BASE}/graphmem/upload`, { method: "POST", body: form });
  await readNdjsonStream(res, onEvent);
}

// Streams one Dream self-maintenance cycle: {phase:"analyze"|"plan"|"pass_start"|
// "pass_done"|"pass_rolled_back"|"done"|"error", ...}. pass_done / pass_rolled_back
// carry a fresh {nodes, links, stats} snapshot.
export async function dreamStream(onEvent, model, domain = "default") {
  const res = await authFetch(`${API_BASE}/graphmem/dream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain, model }),
  });
  await readNdjsonStream(res, onEvent);
}
