// Asks the backend to name a conversation from its first exchange.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchTitle(messages) {
  const res = await fetch(`${API_BASE}/title`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error(`Title request failed: HTTP ${res.status}`);
  const data = await res.json();
  return data.title ?? "";
}
