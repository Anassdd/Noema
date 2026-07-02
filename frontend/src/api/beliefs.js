// The user's own notes/beliefs for a memory context (the selected save, else the live
// domain). Small editable markdown — injected into answers, not indexed. Keyed the same way
// the chat answers (memory || domain), so the editor and the pipeline always agree.
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

export function getBeliefs(domain = "default", memory = null) {
  const params = new URLSearchParams({ domain });
  if (memory) params.set("memory", memory);
  return fetch(`${API_BASE}/beliefs?${params}`).then(asJson);
}

export function saveBeliefs(text, domain = "default", memory = null) {
  return fetch(`${API_BASE}/beliefs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, domain, memory }),
  }).then(asJson);
}

// Append one note (the chat's /note command) without touching existing beliefs. `messages` is
// the recent chat (role/content) so the backend can resolve references ("he"/"that") before
// saving — the claim itself is never altered. Returns { note } = what was actually stored.
export function addBelief(text, domain = "default", memory = null, messages = null) {
  return fetch(`${API_BASE}/beliefs/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, domain, memory, messages }),
  }).then(asJson);
}
