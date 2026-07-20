// Admin-only account management (backend /admin/*). The backend enforces the
// admin session and the self-guards (no self-delete, no self-revoke) — these
// calls just surface its answers, including the human `detail` on refusals.
import { API_BASE, asJson, authFetch } from "./client.js";

const userUrl = (username, action = "") =>
  `${API_BASE}/admin/users/${encodeURIComponent(username)}${action}`;

const post = (url, body) =>
  authFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(asJson);

export const listUsers = () =>
  authFetch(`${API_BASE}/admin/users`).then(asJson);

export const renameUser = (username, newUsername) =>
  post(userUrl(username, "/rename"), { username: newUsername });

export const setUserPassword = (username, password) =>
  post(userUrl(username, "/password"), { password });

export const setUserAdmin = (username, isAdmin) =>
  post(userUrl(username, "/admin"), { is_admin: isAdmin });

export const deleteUser = (username) =>
  authFetch(userUrl(username), { method: "DELETE" }).then(asJson);
