// Client for the persistent memory store (facts saved via /remember). The
// backend keeps these in a JSON file, so they survive reloads and are shared
// across sessions — unlike the per-session character.
import { API_BASE, authFetch } from "./client.js";

export async function fetchMemories() {
  const res = await authFetch(`${API_BASE}/memory`);
  if (!res.ok) throw new Error(`Failed to load memory: HTTP ${res.status}`);
  const data = await res.json();
  return data.memories ?? [];
}

export async function saveMemory(fact) {
  const res = await authFetch(`${API_BASE}/memory`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fact }),
  });
  if (!res.ok) throw new Error(`Failed to save memory: HTTP ${res.status}`);
  const data = await res.json();
  return data.memories ?? [];
}

export async function removeMemoryFact(fact) {
  const res = await authFetch(`${API_BASE}/memory/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fact }),
  });
  if (!res.ok) throw new Error(`Failed to remove fact: HTTP ${res.status}`);
  const data = await res.json();
  return data.memories ?? [];
}

export async function clearMemory() {
  const res = await authFetch(`${API_BASE}/memory`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to clear memory: HTTP ${res.status}`);
  const data = await res.json();
  return data.memories ?? [];
}

// LLM-judged memory: hand the recent exchange to the backend, which decides
// what (if anything) is worth remembering. Returns { added, memories }.
export async function autoMemory(messages) {
  const res = await authFetch(`${API_BASE}/memory/auto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error(`Memory judge failed: HTTP ${res.status}`);
  const data = await res.json();
  return { added: data.added ?? [], memories: data.memories ?? [] };
}
