"""Accounts and sessions: register, login, guest access, logout, whoami.

Also home of `require_user`, the dependency main.py attaches to every other
router — a request without a valid Bearer token gets a 401 before reaching them.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException

from app import auth_store
from app.schemas import Credentials

router = APIRouter(prefix="/auth")

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")
_MIN_PASSWORD_LEN = 6


def require_user(authorization: str = Header(default="")) -> dict:
    """The signed-in user ({'username', 'is_guest'}) behind the Bearer token."""
    token = authorization.removeprefix("Bearer ").strip()
    user = auth_store.resolve(token) if token else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return user


def _session_payload(username: str, token: str, is_guest: bool) -> dict:
    return {"token": token, "username": username, "is_guest": is_guest}


@router.post("/register")
def register(body: Credentials) -> dict:
    username = body.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-24 characters: letters, digits, _ . -",
        )
    if username.lower().startswith("guest-"):
        raise HTTPException(status_code=400, detail="That name is reserved for guests.")
    if len(body.password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {_MIN_PASSWORD_LEN} characters.",
        )
    try:
        token = auth_store.register(username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _session_payload(username, token, is_guest=False)


@router.post("/login")
def login(body: Credentials) -> dict:
    try:
        username, token = auth_store.login(body.username.strip(), body.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    return _session_payload(username, token, is_guest=False)


@router.post("/guest")
def guest() -> dict:
    username, token = auth_store.guest()
    return _session_payload(username, token, is_guest=True)


@router.post("/logout", status_code=204)
def logout(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if token:
        auth_store.logout(token)


@router.get("/me")
def me(authorization: str = Header(default="")) -> dict:
    return require_user(authorization)
