// The gate in front of the app: sign in, create an account, or continue as a
// guest. On success the session is already persisted (api/auth.js) — this just
// hands it up so the app renders.
import { useState } from "react";

import { guestLogin, login, register } from "../api/auth.js";
import { applyTheme, savedDarkMode, savedThemeFamily } from "../lib/theme.js";
import { MoonIcon, SunIcon } from "./icons.jsx";

const field = {
  width: "100%",
  padding: "9px 12px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "transparent",
  color: "var(--text)",
  fontSize: 14,
  outline: "none",
};

export default function AuthPage({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dark, setDark] = useState(savedDarkMode);

  const toggleDark = () => {
    applyTheme(!dark, savedThemeFamily());
    setDark(!dark);
  };

  const creating = mode === "register";

  const run = async (action) => {
    setBusy(true);
    setError("");
    try {
      onAuthed(await action());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    run(() =>
      creating ? register(username.trim(), password) : login(username.trim(), password),
    );
  };

  return (
    <div className="app-bg relative grid h-full w-full place-items-center">
      <button
        onClick={toggleDark}
        aria-label={dark ? "Light mode" : "Dark mode"}
        title={dark ? "Light mode" : "Dark mode"}
        className="absolute right-5 top-5 grid h-8 w-8 place-items-center rounded-[9px] border"
        style={{ borderColor: "var(--border)", color: "var(--text-soft)" }}
      >
        {dark ? <SunIcon size={16} /> : <MoonIcon size={16} />}
      </button>
      <div
        className="glass-panel w-[340px] rounded-2xl border p-7"
        style={{
          borderColor: "var(--border)",
          color: "var(--text)",
          boxShadow: "0 1px 3px rgba(0,0,0,0.05), 0 16px 40px rgba(0,0,0,0.07)",
        }}
      >
        <div
          className="font-serif mb-1 text-center text-[24px]"
          style={{
            fontWeight: "var(--wordmark-weight)",
            letterSpacing: "var(--wordmark-tracking)",
          }}
        >
          Noema
        </div>
        <div className="mb-6 text-center text-[13px]" style={{ color: "var(--text-soft)" }}>
          {creating ? "Create your account" : "Sign in to continue"}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-3">
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Username"
            autoFocus
            autoComplete="username"
            disabled={busy}
            style={field}
          />
          <input
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={creating ? "Password (min. 6 characters)" : "Password"}
            type="password"
            autoComplete={creating ? "new-password" : "current-password"}
            disabled={busy}
            style={field}
          />
          {error && (
            <div className="text-[12.5px]" style={{ color: "var(--danger)" }}>
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={busy || !username.trim() || !password}
            className="mt-1 rounded-[10px] py-2 text-[14px] font-medium text-white"
            style={{
              background: "var(--accent)",
              opacity: busy || !username.trim() || !password ? 0.5 : 1,
            }}
          >
            {creating ? "Create account" : "Sign in"}
          </button>
        </form>

        <button
          onClick={() => {
            setMode(creating ? "login" : "register");
            setError("");
          }}
          disabled={busy}
          className="mt-4 w-full text-center text-[12.5px]"
          style={{ color: "var(--accent)" }}
        >
          {creating ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>

        <div
          className="my-4 flex items-center gap-3 text-[11px]"
          style={{ color: "var(--text-faint)" }}
        >
          <div className="h-px flex-1" style={{ background: "var(--border)" }} />
          or
          <div className="h-px flex-1" style={{ background: "var(--border)" }} />
        </div>

        <button
          onClick={() => run(guestLogin)}
          disabled={busy}
          className="w-full rounded-[10px] border py-2 text-[13.5px]"
          style={{ borderColor: "var(--border)", color: "var(--text-soft)" }}
        >
          Continue as guest
        </button>
        <div
          className="mt-2 text-center text-[11px] leading-relaxed"
          style={{ color: "var(--text-faint)" }}
        >
          Guest chats are temporary — they disappear when the guest session ends.
        </div>
      </div>
    </div>
  );
}
