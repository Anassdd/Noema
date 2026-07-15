// Uploads a PDF to the backend, which extracts and returns its text.
// Returns { filename, pages, chars, text }.
import { API_BASE, authFetch } from "./client.js";

export async function uploadPdf(file) {
  const form = new FormData();
  form.append("file", file);

  const res = await authFetch(`${API_BASE}/upload`, { method: "POST", body: form });
  if (!res.ok) {
    // Surface the backend's human message (e.g. "scanned PDF", "too large").
    let detail = `Upload failed: HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body — keep the generic message */
    }
    throw new Error(detail);
  }
  return res.json();
}
