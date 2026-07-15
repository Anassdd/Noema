// The one place the backend's address and shared response plumbing live.
// Every module in api/ imports from here — change the base URL or error shape once.

export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// ---- Session (who is signed in) ---------------------------------------------
// The token + identity live in localStorage; authFetch below attaches the token
// to every API call and boots back to the login gate when the backend says 401.

const TOKEN_KEY = "noema_token";
const USER_KEY = "noema_user";
const GUEST_KEY = "noema_guest";

export function getSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return null;
  return {
    token,
    username: localStorage.getItem(USER_KEY) ?? "",
    isGuest: localStorage.getItem(GUEST_KEY) === "1",
  };
}

export function setSession({ token, username, is_guest }) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, username);
  localStorage.setItem(GUEST_KEY, is_guest ? "1" : "0");
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(GUEST_KEY);
}

// fetch with the session token attached. On 401 (expired/revoked session) the
// stale session is dropped and the page reloads, which lands on the login gate.
export async function authFetch(url, options = {}) {
  const session = getSession();
  const headers = { ...(options.headers ?? {}) };
  if (session) headers.Authorization = `Bearer ${session.token}`;
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401 && session) {
    clearSession();
    window.location.reload();
  }
  return res;
}

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
