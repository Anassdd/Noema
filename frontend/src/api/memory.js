// Client for the persistent memory store (facts captured by the auto-judge or
// /remember). The backend keeps them in a per-user markdown file (one bullet per
// fact, hand-editable), so they survive reloads and are shared across sessions —
// unlike the per-session character.
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

// The memory file itself — the panel edits it as free markdown. Facts are its
// "- " bullet lines; anything else the user writes is preserved verbatim.
export async function fetchMemoryMarkdown() {
  const res = await authFetch(`${API_BASE}/memory/markdown`);
  if (!res.ok) throw new Error(`Failed to load memory file: HTTP ${res.status}`);
  const data = await res.json();
  return data.markdown ?? "";
}

export async function saveMemoryMarkdown(markdown) {
  const res = await authFetch(`${API_BASE}/memory/markdown`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ markdown }),
  });
  if (!res.ok) throw new Error(`Failed to save memory file: HTTP ${res.status}`);
  const data = await res.json();
  return { markdown: data.markdown ?? "", memories: data.memories ?? [] };
}

export async function clearMemory() {
  const res = await authFetch(`${API_BASE}/memory`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to clear memory: HTTP ${res.status}`);
  const data = await res.json();
  return data.memories ?? [];
}

// Automatic memory evolution: hand the recent exchange to the backend judge,
// which adds / updates / deletes facts and routes asserted domain opinions into
// the current memory context's beliefs. `domain`/`memory` say which context that
// is (the same values the chat answers with).
export async function autoMemory(messages, domain = "default", memory = null) {
  const res = await authFetch(`${API_BASE}/memory/auto`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, domain, memory }),
  });
  if (!res.ok) throw new Error(`Memory judge failed: HTTP ${res.status}`);
  const data = await res.json();
  return {
    added: data.added ?? [],
    updated: data.updated ?? [],
    removed: data.removed ?? [],
    beliefsAdded: data.beliefs_added ?? [],
    consolidated: data.consolidated ?? false,
    memories: data.memories ?? [],
  };
}
