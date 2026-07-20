"""Admin-only account management: list, rename, reset password, admin flag, delete.

Admins are the first registered account, anyone granted the flag here, or the
ADMIN_USERS env override. Two guards keep at least one admin alive: you cannot
delete your own account, and you cannot revoke your own admin rights.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import auth_store, saves
from app.routers.auth import _MIN_PASSWORD_LEN, _USERNAME_RE, require_user
from app.schemas import AdminFlag, AdminPassword, AdminRename

router = APIRouter(prefix="/admin")


def require_admin(user: dict = Depends(require_user)) -> dict:
    """The signed-in admin behind the request, or a 403."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def block_bench_writes(user: dict, domain: str = "", save_name: str = "") -> None:
    """Refuse non-admin modification of bench-built content (the expensive frozen
    benchmark corpora). Everything else — other saves, live domains, notes — stays
    open to everyone."""
    if user.get("is_admin"):
        return
    if saves.is_bench_artifact(domain, save_name):
        raise HTTPException(
            status_code=403,
            detail="Benchmark dataset content is read-only — an admin account is "
                   "needed to modify or delete it.",
        )


def _is_self(username: str, user: dict) -> bool:
    return username.lower() == user["username"].lower()


@router.get("/users")
def list_users(user: dict = Depends(require_admin)) -> list[dict]:
    return [
        {**record, "is_self": _is_self(record["username"], user)}
        for record in auth_store.list_users()
    ]


@router.post("/users/{username}/rename")
def rename(username: str, body: AdminRename, user: dict = Depends(require_admin)) -> dict:
    new = body.username.strip()
    if not _USERNAME_RE.match(new):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-24 characters: letters, digits, _ . -",
        )
    if new.lower().startswith("guest-"):
        raise HTTPException(status_code=400, detail="That name is reserved for guests.")
    try:
        auth_store.rename_user(username, new)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"username": new}


@router.post("/users/{username}/password")
def set_password(
    username: str, body: AdminPassword, user: dict = Depends(require_admin)
) -> dict:
    if len(body.password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {_MIN_PASSWORD_LEN} characters.",
        )
    try:
        auth_store.set_password(username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"username": username, "signed_out": True}


@router.post("/users/{username}/admin")
def set_admin(username: str, body: AdminFlag, user: dict = Depends(require_admin)) -> dict:
    if _is_self(username, user) and not body.is_admin:
        raise HTTPException(
            status_code=400, detail="You cannot revoke your own admin rights."
        )
    try:
        auth_store.set_admin(username, body.is_admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"username": username, "is_admin": auth_store.is_admin(username)}


@router.delete("/users/{username}")
def delete_account(username: str, user: dict = Depends(require_admin)) -> dict:
    if _is_self(username, user):
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    try:
        auth_store.delete_account(username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"deleted": username}
