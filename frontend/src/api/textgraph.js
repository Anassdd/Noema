// The co-occurrence graph memory API. The graph persists on the backend, so the
// page just loads the current snapshot on open and folds in whatever you ingest.
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

export function getGraph(limit = 160) {
  return fetch(`${API_BASE}/textgraph?limit=${limit}`).then(asJson);
}

export function ingestText(text, source, limit = 160) {
  return fetch(`${API_BASE}/textgraph/ingest?limit=${limit}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, source }),
  }).then(asJson);
}

export function uploadPdf(file, model, limit = 160) {
  const form = new FormData();
  form.append("file", file);
  if (model) form.append("model", model);
  return fetch(`${API_BASE}/textgraph/upload?limit=${limit}`, {
    method: "POST",
    body: form,
  }).then(asJson);
}

export function resetGraph() {
  return fetch(`${API_BASE}/textgraph/reset`, { method: "POST" }).then(asJson);
}
