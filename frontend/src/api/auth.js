// Sign-in surface. register/login/guestLogin persist the returned session so
// every later authFetch call carries it. These use plain fetch on purpose —
// there's no session yet, and a wrong password (401) must not trigger the
// authFetch reload-to-gate behavior.
import { API_BASE, asJson, clearSession, getSession, setSession } from "./client.js";

async function startSession(path, body) {
  const session = await fetch(`${API_BASE}/auth/${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).then(asJson);
  setSession(session);
  return session;
}

export const register = (username, password) =>
  startSession("register", { username, password });

export const login = (username, password) =>
  startSession("login", { username, password });

export const guestLogin = () => startSession("guest");

export async function logout() {
  const session = getSession();
  if (session) {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${session.token}` },
    }).catch(() => {});
  }
  clearSession();
}
