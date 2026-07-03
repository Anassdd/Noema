// The one place the backend's address and shared response plumbing live.
// Every module in api/ imports from here — change the base URL or error shape once.

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// Resolve a fetch Response to JSON, surfacing the backend's human `detail` on errors.
export async function asJson(res) {
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

// Consume an NDJSON streaming response (one JSON object per line), calling
// onEvent per parsed line. Used by graph ingestion and Dream.
export async function readNdjsonStream(res, onEvent) {
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
