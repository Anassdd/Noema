// Client for the persistent memory store — three markdown files per account
// (profile / now / history) evolved by the auto-judge and /remember. Every
// endpoint returns the same full state, parsed here once:
//   memories — the live facts (profile + now), for the panel list and /forget
//   context  — the composed injection block for the system prompt
//   files    — the three files verbatim, for the settings editor
//   usage    — chars/cap gauges for the capped live files
import { API_BASE, authFetch } from "./client.js";

function parseState(data) {
  return {
    memories: data.memories ?? [],
    context: data.context ?? null,
    files: data.files ?? null,
    usage: data.usage ?? null,
  };
}

async function request(path, options) {
  const res = await authFetch(`${API_BASE}${path}`, options);
  if (!res.ok) throw new Error(`Memory request failed: HTTP ${res.status}`);
  return res.json();
}

const post = (body) => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

// Session start — also triggers the backend's daily expiry sweep.
export async function fetchMemory() {
  return parseState(await request("/memory"));
}

export async function saveMemory(fact) {
  return parseState(await request("/memory", post({ fact })));
}

export async function removeMemoryFact(fact) {
  return parseState(await request("/memory/remove", post({ fact })));
}

export async function clearMemory() {
  return parseState(await request("/memory", { method: "DELETE" }));
}

// One memory file, edited as free markdown — facts are its "- " bullet lines,
// anything else written around them is preserved verbatim.
export async function saveMemoryFile(name, markdown) {
  return parseState(
    await request(`/memory/files/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ markdown }),
    }),
  );
}

// Automatic memory evolution: hand the recent exchange to the backend judge,
// which adds / updates / retires / moves facts and routes asserted domain
// opinions into the current memory context's beliefs. `domain`/`memory` say
// which context that is (the same values the chat answers with).
export async function autoMemory(messages, domain = "default", memory = null) {
  const data = await request("/memory/auto", post({ messages, domain, memory }));
  return {
    added: data.added ?? [],
    updated: data.updated ?? [],
    removed: data.removed ?? [],
    retired: [...(data.retired ?? []), ...(data.archived ?? [])],
    profileUpdated: data.profile_updated ?? [],
    beliefsAdded: data.beliefs_added ?? [],
    beliefsUpdated: data.beliefs_updated ?? [],
    consolidated: data.consolidated ?? false,
    state: parseState(data),
  };
}
