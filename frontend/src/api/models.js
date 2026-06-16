// Fetches the models available at the endpoint plus the configured default.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function fetchModels() {
  const res = await fetch(`${API_BASE}/models`);
  if (!res.ok) throw new Error(`Failed to load models: HTTP ${res.status}`);
  const data = await res.json();
  return { models: data.models ?? [], default: data.default ?? "" };
}
