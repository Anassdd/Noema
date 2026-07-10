// The LightRAG memory engine — same payload shape and NDJSON upload protocol as
// graphmem.js, so the graph page swaps engines by swapping which module it calls.
import { API_BASE, asJson, readNdjsonStream } from "./client.js";

export function getLightragGraph(domain = "default") {
  return fetch(`${API_BASE}/lightragmem?domain=${domain}`).then(asJson);
}

export function ingestLightragText(text, model, source, domain = "default") {
  return fetch(`${API_BASE}/lightragmem/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model, source, domain }),
  }).then(asJson);
}

export function resetLightrag(domain = "default") {
  return fetch(`${API_BASE}/lightragmem/reset?domain=${domain}`, { method: "POST" }).then(asJson);
}

// Streams the per-batch extraction: {phase:"parsing"|"parsed"|"page"|"error"|"done", ...}.
// A "page" event carries a fresh {nodes, links, stats} snapshot.
export async function uploadLightragPdfStream(file, model, onEvent, domain = "default") {
  const form = new FormData();
  form.append("file", file);
  if (model) form.append("model", model);
  form.append("domain", domain);
  const res = await fetch(`${API_BASE}/lightragmem/upload`, { method: "POST", body: form });
  await readNdjsonStream(res, onEvent);
}
