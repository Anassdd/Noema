"""Durable conversation storage, backed by SQLite (stdlib — no extra dependency).

Each conversation is one row; its messages + persona + attached documents live
in a single JSON `data` column, so there's no practical size limit and the whole
thread loads in one read. The DB file sits next to this module and is
gitignored/disposable — delete it to reset all conversations.

Every row has an `owner` (a username from auth_store). Visibility rule: you see
your own conversations, and registered accounts also see legacy rows saved
before accounts existed (owner = ''). Guests only ever see their own.

This is separate from memory_store (user facts): this holds the conversations
themselves.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.config import state_path

_DB_PATH = state_path("conversations", Path(__file__).resolve().parent) / "conversations.db"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    with closing(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                data        TEXT NOT NULL,
                owner       TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(conversations)")}
        if "owner" not in columns:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN owner TEXT NOT NULL DEFAULT ''"
            )
        conn.commit()


_init()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _visibility_clause(is_guest: bool) -> str:
    return "owner = ?" if is_guest else "(owner = ? OR owner = '')"


def list_summaries(username: str, is_guest: bool) -> list[dict]:
    """Lightweight rows for the sidebar (no message bodies), recent first."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            f"WHERE {_visibility_clause(is_guest)} ORDER BY updated_at DESC",
            (username,),
        ).fetchall()
    return [dict(row) for row in rows]


def get(conversation_id: str, username: str, is_guest: bool) -> dict | None:
    """The full conversation (messages + persona + documents), or None."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, data FROM conversations "
            f"WHERE id = ? AND {_visibility_clause(is_guest)}",
            (conversation_id, username),
        ).fetchone()
    if row is None:
        return None
    data = json.loads(row["data"])
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "messages": data.get("messages", []),
        "character": data.get("character", ""),
        "documents": data.get("documents", []),
    }


def upsert(
    conversation_id: str,
    title: str,
    character: str,
    messages: list,
    documents: list,
    username: str,
    is_guest: bool,
) -> dict | None:
    """Create or update a conversation. Returns its (new) summary, or None if
    the id belongs to someone else. Legacy rows keep owner = '' (still shared)."""
    now = _now()
    data = json.dumps(
        {"messages": messages, "character": character, "documents": documents},
        ensure_ascii=False,
    )
    with closing(_connect()) as conn:
        existing = conn.execute(
            "SELECT created_at, owner FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if existing is not None:
            visible = existing["owner"] == username or (
                existing["owner"] == "" and not is_guest
            )
            if not visible:
                return None
        created_at = existing["created_at"] if existing else now
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at, data, owner) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "title = excluded.title, updated_at = excluded.updated_at, "
            "data = excluded.data",
            (conversation_id, title, created_at, now, data, username),
        )
        conn.commit()
    return {
        "id": conversation_id,
        "title": title,
        "created_at": created_at,
        "updated_at": now,
    }


def rename(conversation_id: str, title: str, username: str, is_guest: bool) -> bool:
    """Update only the title (used by auto-titling). Returns False if missing."""
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? "
            f"WHERE id = ? AND {_visibility_clause(is_guest)}",
            (title, _now(), conversation_id, username),
        )
        conn.commit()
        return cur.rowcount > 0


def delete(conversation_id: str, username: str, is_guest: bool) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute(
            f"DELETE FROM conversations WHERE id = ? AND {_visibility_clause(is_guest)}",
            (conversation_id, username),
        )
        conn.commit()
        return cur.rowcount > 0


def clear(username: str, is_guest: bool) -> None:
    """Delete every conversation this user can see (the "clear history" action)."""
    with closing(_connect()) as conn:
        conn.execute(
            f"DELETE FROM conversations WHERE {_visibility_clause(is_guest)}",
            (username,),
        )
        conn.commit()


def delete_all_owned_by(username: str) -> None:
    """Guest cleanup: drop a departed guest's conversations."""
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM conversations WHERE owner = ?", (username,))
        conn.commit()
