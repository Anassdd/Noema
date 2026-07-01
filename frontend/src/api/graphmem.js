// The real graph memory (Graphiti). Extraction is slow, so PDF upload streams
// NDJSON — one event per page — and the page draws the graph as it grows.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function asJson(res) {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep generic */
    }
    throw new Error(detail);
  }
  return res.json();
}

export function getGraph(domain = "default") {
  return fetch(`${API_BASE}/graphmem?domain=${domain}`).then(asJson);
}

export function ingestText(text, model, source, domain = "default") {
  return fetch(`${API_BASE}/graphmem/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model, source, domain }),
  }).then(asJson);
}

export function resetGraph(domain = "default") {
  return fetch(`${API_BASE}/graphmem/reset?domain=${domain}`, { method: "POST" }).then(asJson);
}

// Save / restore full-graph checkpoints (so you can experiment and roll back).
export function listSaves(domain = "default") {
  return fetch(`${API_BASE}/graphmem/saves?domain=${domain}`).then(asJson);
}

function savePost(path, name, domain) {
  return fetch(`${API_BASE}/graphmem/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, domain }),
  }).then(asJson);
}

export const saveGraph = (name, domain = "default") => savePost("save", name, domain);
export const restoreGraph = (name, domain = "default") => savePost("restore", name, domain);
export const deleteSave = (name, domain = "default") => savePost("delete-save", name, domain);

// Streams the per-page extraction. `onEvent` is called for each NDJSON line:
// {phase:"parsing"|"parsed"|"page"|"error"|"done", ...}. A "page" event carries a
// fresh {nodes, links, stats} snapshot.
export async function uploadPdfStream(file, model, onEvent, domain = "default") {
  const form = new FormData();
  form.append("file", file);
  if (model) form.append("model", model);
  form.append("domain", domain);

  const res = await fetch(`${API_BASE}/graphmem/upload`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep generic */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer.trim()));
}
