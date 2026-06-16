"""Durable conversation storage, backed by SQLite (stdlib — no extra dependency).

Each conversation is one row; its messages + persona + attached documents live
in a single JSON `data` column, so there's no practical size limit and the whole
thread loads in one read. The DB file sits next to this module and is
gitignored/disposable — delete it to reset all conversations.

This is separate from memory_store (user facts): this holds the conversations
themselves.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent / "conversations.db"


def _connect() -> sqlite3.Connection:
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
                data        TEXT NOT NULL
            )
            """
        )
        conn.commit()


_init()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_summaries() -> list[dict]:
    """Lightweight rows for the sidebar (no message bodies), recent first."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations "
            "ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get(conversation_id: str) -> dict | None:
    """The full conversation (messages + persona + documents), or None."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, data FROM conversations "
            "WHERE id = ?",
            (conversation_id,),
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
) -> dict:
    """Create or replace a conversation. Returns its (new) summary."""
    now = _now()
    data = json.dumps(
        {"messages": messages, "character": character, "documents": documents},
        ensure_ascii=False,
    )
    with closing(_connect()) as conn:
        existing = conn.execute(
            "SELECT created_at FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "title = excluded.title, updated_at = excluded.updated_at, "
            "data = excluded.data",
            (conversation_id, title, created_at, now, data),
        )
        conn.commit()
    return {
        "id": conversation_id,
        "title": title,
        "created_at": created_at,
        "updated_at": now,
    }


def rename(conversation_id: str, title: str) -> bool:
    """Update only the title (used by auto-titling). Returns False if missing."""
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, _now(), conversation_id),
        )
        conn.commit()
        return cur.rowcount > 0


def delete(conversation_id: str) -> bool:
    with closing(_connect()) as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ?", (conversation_id,)
        )
        conn.commit()
        return cur.rowcount > 0


def clear() -> None:
    """Delete every conversation (the "clear history" action)."""
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM conversations")
        conn.commit()
