import { useEffect, useState } from "react";

import ConfirmDialog from "../components/ConfirmDialog.jsx";
import {
  KeyIcon,
  PencilIcon,
  ShieldIcon,
  TrashIcon,
  UsersIcon,
} from "../components/icons.jsx";
import {
  deleteUser,
  listUsers,
  renameUser,
  setUserAdmin,
  setUserPassword,
} from "../api/admin.js";
import { getSession } from "../api/client.js";
import { refreshIdentity } from "../api/auth.js";

const field = {
  width: "100%",
  padding: "8px 11px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "transparent",
  color: "var(--text)",
  fontSize: 13.5,
  outline: "none",
};

// The admin surface — its own tab (?view=admin), in the app's theme. Lists every
// registered account with inline rename / password-reset editors, an admin
// toggle, and delete (confirmed). The backend enforces admin access and the
// self-guards; resetting your OWN password signs you out everywhere.
export default function AdminPage() {
  const [session, setSession] = useState(getSession);

  // Admin rights may have been granted after this tab's session was stored.
  useEffect(() => {
    if (!session?.isAdmin) refreshIdentity().then((s) => s && setSession(s));
  }, []);

  return (
    <div
      className="app-bg fixed inset-0 overflow-y-auto"
      style={{ color: "var(--text)" }}
    >
      <div className="mx-auto w-full max-w-2xl px-4 py-8">
        <div
          className="glass-panel overflow-hidden rounded-2xl"
          style={{ border: "1px solid var(--border)" }}
        >
          <div
            className="flex items-center justify-between px-6 pt-6"
            style={{ color: "var(--text)" }}
          >
            <div className="flex items-center gap-3">
              <span
                className="grid h-9 w-9 place-items-center rounded-[10px] border"
                style={{
                  borderColor: "var(--accent-border)",
                  background: "var(--accent-soft)",
                  color: "var(--accent)",
                }}
              >
                <UsersIcon size={18} />
              </span>
              <div>
                <h1 className="font-serif text-lg" style={{ fontWeight: "var(--title-weight)" }}>
                  Noema · Administration
                </h1>
                <div className="text-xs" style={{ color: "var(--text-soft)" }}>
                  Accounts: rename, reset passwords, admin rights, delete.
                </div>
              </div>
            </div>
            <a
              href={`${window.location.origin}/`}
              className="rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition hover:bg-[var(--row-hover)]"
              style={{ borderColor: "var(--border)", color: "var(--text-soft)", textDecoration: "none" }}
            >
              Open chat ↗
            </a>
          </div>

          {session?.isAdmin ? (
            <Accounts />
          ) : (
            <div className="px-6 pb-8 pt-6 text-sm" style={{ color: "var(--text-soft)" }}>
              This page needs an admin account. You are signed in as{" "}
              <b style={{ color: "var(--text)" }}>{session?.username || "nobody"}</b> — ask an
              admin to grant you access, or sign in with the admin account.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Accounts() {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(null); // {username, mode: "rename"|"password"}
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);

  const load = () =>
    listUsers()
      .then((list) => {
        setUsers(list);
        setError("");
      })
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  // Run one admin action, then refresh the list. A rename of our own account also
  // re-syncs the stored session so every tab shows the new name.
  const perform = async (action, touchedSelf) => {
    setBusy(true);
    setError("");
    try {
      await action();
      setEditing(null);
      if (touchedSelf) await refreshIdentity();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-6 pb-6 pt-4">
      {error && (
        <div
          className="mb-3 rounded-lg border px-3 py-2 text-[12.5px]"
          style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
        >
          {error}
        </div>
      )}

      {users === null && !error && (
        <div className="py-6 text-center text-sm" style={{ color: "var(--text-faint)" }}>
          Loading accounts…
        </div>
      )}
      {users?.length === 0 && (
        <div className="py-6 text-center text-sm" style={{ color: "var(--text-faint)" }}>
          No registered accounts yet.
        </div>
      )}
      {users?.map((u) => (
        <UserRow
          key={u.username}
          user={u}
          busy={busy}
          editing={editing?.username === u.username ? editing.mode : null}
          onEdit={(mode) =>
            setEditing(
              editing?.username === u.username && editing.mode === mode
                ? null
                : { username: u.username, mode }
            )
          }
          onRename={(name) => perform(() => renameUser(u.username, name), u.is_self)}
          onPassword={(password) => perform(() => setUserPassword(u.username, password), false)}
          onToggleAdmin={() => perform(() => setUserAdmin(u.username, !u.is_admin), false)}
          onDelete={() => setPendingDelete(u.username)}
        />
      ))}

      {pendingDelete !== null && (
        <ConfirmDialog
          title={`Delete ${pendingDelete}?`}
          message="The account, its conversations, memory and beliefs will be permanently removed. This can't be undone."
          confirmLabel="Delete account"
          onConfirm={() => {
            perform(() => deleteUser(pendingDelete), false);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}

function UserRow({
  user,
  busy,
  editing,
  onEdit,
  onRename,
  onPassword,
  onToggleAdmin,
  onDelete,
}) {
  const created = user.created_at?.slice(0, 10);
  return (
    <div className="py-2.5" style={{ borderTop: "1px solid var(--border-soft)" }}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <span className="truncate">{user.username}</span>
            {user.is_admin && <Chip accent>admin</Chip>}
            {user.is_self && <Chip>you</Chip>}
          </div>
          <div className="text-[11px]" style={{ color: "var(--text-faint)" }}>
            since {created}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <RowAction
            title="Rename"
            active={editing === "rename"}
            disabled={busy}
            onClick={() => onEdit("rename")}
            icon={<PencilIcon size={14} />}
          />
          <RowAction
            title="Set a new password"
            active={editing === "password"}
            disabled={busy}
            onClick={() => onEdit("password")}
            icon={<KeyIcon size={14} />}
          />
          <RowAction
            title={
              user.is_self
                ? "You cannot revoke your own admin rights"
                : user.is_admin
                  ? "Revoke admin"
                  : "Make admin"
            }
            active={user.is_admin}
            disabled={busy || user.is_self}
            onClick={onToggleAdmin}
            icon={<ShieldIcon size={14} />}
          />
          <RowAction
            title={user.is_self ? "You cannot delete your own account" : "Delete account"}
            danger
            disabled={busy || user.is_self}
            onClick={onDelete}
            icon={<TrashIcon size={14} />}
          />
        </div>
      </div>

      {editing === "rename" && (
        <InlineEditor
          key="rename"
          placeholder="New username"
          confirmLabel="Rename"
          busy={busy}
          onSubmit={onRename}
          hint={user.is_self ? "This renames your own account." : null}
        />
      )}
      {editing === "password" && (
        <InlineEditor
          key="password"
          placeholder="New password (min. 6 characters)"
          confirmLabel="Set password"
          type="password"
          busy={busy}
          onSubmit={onPassword}
          hint={
            user.is_self
              ? "This signs you out everywhere — including here."
              : "Signs them out everywhere; tell them the new password."
          }
        />
      )}
    </div>
  );
}

function InlineEditor({ placeholder, confirmLabel, type = "text", busy, onSubmit, hint }) {
  const [value, setValue] = useState("");
  const submit = () => value.trim() && onSubmit(value.trim());
  return (
    <div className="mt-2">
      <div className="flex items-center gap-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder={placeholder}
          type={type}
          autoFocus
          disabled={busy}
          style={field}
        />
        <button
          onClick={submit}
          disabled={busy || !value.trim()}
          className="whitespace-nowrap rounded-lg px-3 py-2 text-[12.5px] font-medium transition disabled:cursor-default disabled:opacity-50"
          style={{ background: "var(--send-bg)", color: "var(--send-fg)" }}
        >
          {confirmLabel}
        </button>
      </div>
      {hint && (
        <div className="mt-1 text-[11px]" style={{ color: "var(--text-faint)" }}>
          {hint}
        </div>
      )}
    </div>
  );
}

function Chip({ children, accent }) {
  return (
    <span
      className="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
      style={
        accent
          ? { background: "var(--accent-soft)", color: "var(--accent)" }
          : { background: "var(--row-active)", color: "var(--text-soft)" }
      }
    >
      {children}
    </span>
  );
}

function RowAction({ title, icon, onClick, disabled, active, danger }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="grid h-7 w-7 place-items-center rounded-lg transition hover:bg-[var(--row-hover)] disabled:cursor-default disabled:opacity-40"
      style={{
        color: danger ? "var(--danger)" : active ? "var(--accent)" : "var(--text-soft)",
      }}
    >
      {icon}
    </button>
  );
}
