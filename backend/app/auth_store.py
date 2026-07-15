"""File-backed accounts and sessions — the "no database yet" auth layer.

Two JSON files under backend/data/auth/ (gitignored): users.json holds salted
PBKDF2-SHA256 password hashes (never the passwords), sessions.json maps opaque
random tokens to who's signed in. Guests get a normal session flagged is_guest,
so the rest of the backend has one code path. Everything is stdlib — no new
packages on the locked-down machine. Swapping this for a real database later
only means reimplementing the functions below.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import beliefs, conversation_store, memory_store

_AUTH_DIR = Path(__file__).resolve().parents[1] / "data" / "auth"
_USERS_PATH = _AUTH_DIR / "users.json"
_SESSIONS_PATH = _AUTH_DIR / "sessions.json"

_PBKDF2_ITERATIONS = 600_000
_USER_SESSION_DAYS = 30
_GUEST_SESSION_HOURS = 24

_lock = threading.Lock()


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save(path: Path, data: dict) -> None:
    _AUTH_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return digest.hex()


def register(username: str, password: str) -> str:
    """Create the account and sign it in. Returns the session token."""
    with _lock:
        users = _load(_USERS_PATH)
        if username.lower() in users:
            raise ValueError("This username is already taken.")
        salt = secrets.token_hex(16)
        users[username.lower()] = {
            "username": username,
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "created_at": _now().isoformat(),
        }
        _save(_USERS_PATH, users)
    return _mint_session(username, is_guest=False)


def login(username: str, password: str) -> tuple[str, str]:
    """Verify credentials. Returns (canonical username, session token)."""
    users = _load(_USERS_PATH)
    record = users.get(username.lower())
    if record is None or not hmac.compare_digest(
        record["password_hash"], _hash_password(password, record["salt"])
    ):
        raise ValueError("Wrong username or password.")
    return record["username"], _mint_session(record["username"], is_guest=False)


def guest() -> tuple[str, str]:
    """A throwaway signed-in identity. Returns (username, token)."""
    username = f"guest-{secrets.token_hex(2)}"
    return username, _mint_session(username, is_guest=True)


def resolve(token: str) -> dict | None:
    """The user behind a token — {'username', 'is_guest'} — or None."""
    session = _load(_SESSIONS_PATH).get(token)
    if session is None or session["expires_at"] <= _now().isoformat():
        return None
    return {"username": session["username"], "is_guest": session["is_guest"]}


def logout(token: str) -> None:
    with _lock:
        sessions = _load(_SESSIONS_PATH)
        ended = sessions.pop(token, None)
        live = _prune(sessions)
        _save(_SESSIONS_PATH, live)
        if (
            ended
            and ended["is_guest"]
            and all(s["username"] != ended["username"] for s in live.values())
        ):
            _forget_guest(ended["username"])


def _mint_session(username: str, is_guest: bool) -> str:
    token = secrets.token_urlsafe(32)
    ttl = (
        timedelta(hours=_GUEST_SESSION_HOURS)
        if is_guest
        else timedelta(days=_USER_SESSION_DAYS)
    )
    with _lock:
        sessions = _prune(_load(_SESSIONS_PATH))
        sessions[token] = {
            "username": username,
            "is_guest": is_guest,
            "expires_at": (_now() + ttl).isoformat(),
        }
        _save(_SESSIONS_PATH, sessions)
    return token


def _prune(sessions: dict) -> dict:
    """Drop expired sessions; a guest whose last session died takes their
    conversations, memory and beliefs with them (guests are ephemeral by design)."""
    now = _now().isoformat()
    live = {t: s for t, s in sessions.items() if s["expires_at"] > now}
    dead_guests = {
        s["username"] for s in sessions.values() if s["is_guest"]
    } - {s["username"] for s in live.values() if s["is_guest"]}
    for username in dead_guests:
        _forget_guest(username)
    return live


def _forget_guest(username: str) -> None:
    conversation_store.delete_all_owned_by(username)
    memory_store.delete_user(username)
    beliefs.delete_user_files(username)
