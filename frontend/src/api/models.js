// Fetches the models available at the endpoint plus the configured default.
import { API_BASE, authFetch } from "./client.js";

export async function fetchModels() {
  const res = await authFetch(`${API_BASE}/models`);
  if (!res.ok) throw new Error(`Failed to load models: HTTP ${res.status}`);
  const data = await res.json();
  return { models: data.models ?? [], default: data.default ?? "",
           strong: data.default_strong ?? "", judge: data.default_judge ?? "",
           web: data.web_search ?? false, efforts: data.efforts ?? {} };
}
