"""Admin account-management tests — no network, no LLM calls:

    backend/.venv/bin/python tests/test_auth_admin.py

All state is redirected to a scratch dir via NOEMA_STATE_DIR (set BEFORE the app
imports, so every store resolves there — the real auth/conversations/memory files
are never touched). Covers the admin bootstrap rules, the four management
operations (rename carries sessions + personal data along), and the router
guards that keep at least one admin alive.
"""

import os
import sys
import tempfile
from pathlib import Path

_SCRATCH = tempfile.mkdtemp(prefix="noema-admin-test-")
os.environ["NOEMA_STATE_DIR"] = _SCRATCH
os.environ["ADMIN_USERS"] = "forced-admin"
os.environ.setdefault("OPENAI_API_KEY", "test-key-never-called")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi import HTTPException  # noqa: E402

from app import auth_store, beliefs, conversation_store, memory_store  # noqa: E402
from app.routers import admin  # noqa: E402
from app.schemas import AdminFlag, AdminPassword, AdminRename  # noqa: E402


def _admin_map():
    return {u["username"]: u["is_admin"] for u in auth_store.list_users()}


def _expect_400(fn, why):
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == 400, f"{why}: got {exc.status_code}"
        return
    raise AssertionError(f"{why}: no HTTPException raised")


def test_first_account_bootstraps_admin():
    alice_token = auth_store.register("Alice", "password-a")
    auth_store.register("Bob", "password-b")
    assert _admin_map() == {"Alice": True, "Bob": False}
    assert auth_store.resolve(alice_token)["is_admin"] is True
    guest_name, guest_token = auth_store.guest()
    assert auth_store.resolve(guest_token)["is_admin"] is False
    auth_store.logout(guest_token)
    print("  first registered account is admin; later ones and guests are not ✓")


def test_admin_users_env_override():
    auth_store.register("Forced-Admin", "password-f")
    assert _admin_map()["Forced-Admin"] is True, "ADMIN_USERS must win over the record"
    print("  ADMIN_USERS override grants admin without the stored flag ✓")


def test_grant_and_revoke():
    auth_store.set_admin("bob", True)
    assert auth_store.is_admin("Bob") is True
    auth_store.set_admin("bob", False)
    assert auth_store.is_admin("Bob") is False
    print("  grant + revoke round-trips through the stored flag ✓")


def test_rename_carries_sessions_and_data():
    _, bob_token = auth_store.login("Bob", "password-b")
    memory_store.add_fact("Bob", "likes chess", "2026-07-22")
    beliefs.write_beliefs("my note", domain="dom", user="Bob")
    conversation_store.upsert("conv-1", "t", "", [], [], "Bob", is_guest=False)

    auth_store.rename_user("bob", "Bobby")

    assert auth_store.resolve(bob_token)["username"] == "Bobby", "session must follow"
    assert memory_store.live_facts("Bobby") == ["likes chess"]
    assert memory_store.live_facts("Bob") == []
    assert beliefs.read_beliefs(domain="dom", user="Bobby") == "my note"
    assert [s["id"] for s in conversation_store.list_summaries("Bobby", False)] == ["conv-1"]
    try:
        auth_store.login("Bob", "password-b")
        raise AssertionError("old username must stop working")
    except ValueError:
        pass
    auth_store.login("Bobby", "password-b")
    print("  rename carries sessions, memory, beliefs and conversations ✓")


def test_password_reset_revokes_sessions():
    _, token = auth_store.login("Bobby", "password-b")
    auth_store.set_password("bobby", "fresh-password")
    assert auth_store.resolve(token) is None, "old sessions must die on reset"
    try:
        auth_store.login("Bobby", "password-b")
        raise AssertionError("old password must stop working")
    except ValueError:
        pass
    auth_store.login("Bobby", "fresh-password")
    print("  password reset replaces the hash and signs out everywhere ✓")


def test_delete_account_removes_everything():
    auth_store.delete_account("bobby")
    assert "Bobby" not in _admin_map()
    assert memory_store.live_facts("Bobby") == []
    assert beliefs.read_beliefs(domain="dom", user="Bobby") == ""
    assert conversation_store.list_summaries("Bobby", True) == []
    try:
        auth_store.login("Bobby", "fresh-password")
        raise AssertionError("deleted account must not sign in")
    except ValueError:
        pass
    print("  delete removes the account, sessions and personal data ✓")


def test_router_guards():
    plain = {"username": "Alice", "is_guest": False, "is_admin": False}
    boss = {"username": "Alice", "is_guest": False, "is_admin": True}
    try:
        admin.require_admin(plain)
        raise AssertionError("non-admin must get a 403")
    except HTTPException as exc:
        assert exc.status_code == 403
    _expect_400(lambda: admin.delete_account("alice", user=boss), "self-delete")
    _expect_400(
        lambda: admin.set_admin("ALICE", AdminFlag(is_admin=False), user=boss),
        "self-revoke",
    )
    _expect_400(
        lambda: admin.rename("Alice", AdminRename(username="a!"), user=boss),
        "invalid username",
    )
    _expect_400(
        lambda: admin.set_password("nobody", AdminPassword(password="long-enough"), user=boss),
        "unknown account",
    )
    assert admin.set_admin("alice", AdminFlag(is_admin=True), user=boss)["is_admin"]
    print("  router guards: 403 for non-admins, 400 on self-delete/self-revoke ✓")


def test_default_admin_seeding():
    from dataclasses import replace

    from app.config import Settings

    # The out-of-the-box contract: every deployment boots with admin/admin.
    assert Settings.__dataclass_fields__["admin_username"].default == "admin"
    assert Settings.__dataclass_fields__["admin_password"].default == "admin"

    real = auth_store.settings
    try:
        # Missing account + password configured -> created as a working admin.
        auth_store.settings = replace(real, admin_username="Boss", admin_password="boot-secret")
        auth_store.ensure_default_admin()
        assert auth_store.is_admin("Boss")
        auth_store.login("Boss", "boot-secret")
        # Re-seeding after a password change must NOT reset it back.
        auth_store.set_password("boss", "changed-later")
        auth_store.ensure_default_admin()
        auth_store.login("Boss", "changed-later")
        # An existing account gets promoted; its own password stays untouched.
        auth_store.register("Norm", "password-n")
        auth_store.settings = replace(real, admin_username="Norm", admin_password="ignored")
        auth_store.ensure_default_admin()
        assert auth_store.is_admin("Norm")
        auth_store.login("Norm", "password-n")
        # No password configured + missing account -> nothing is created.
        auth_store.settings = replace(real, admin_username="ghost", admin_password="")
        auth_store.ensure_default_admin()
        assert "ghost" not in {u["username"].lower() for u in auth_store.list_users()}
    finally:
        auth_store.settings = real
    print("  startup seeding: creates or promotes the .env admin, never re-passwords ✓")


def test_bench_write_guard():
    from app import saves

    assert saves.is_bench_artifact(name="bench-qasper-100k-abc123")
    assert saves.is_bench_artifact("__save__default__bench-qasper-100k-abc123")
    assert not saves.is_bench_artifact("default")
    assert not saves.is_bench_artifact("__save__default__my-checkpoint")
    assert not saves.is_bench_artifact("__save__malformed-no-name")

    plain = {"username": "u", "is_guest": False, "is_admin": False}
    boss = {"username": "a", "is_guest": False, "is_admin": True}
    admin.block_bench_writes(boss, "__save__default__bench-x")   # admins pass
    admin.block_bench_writes(plain, "default")                   # live domains stay open
    admin.block_bench_writes(plain, "default", "my-checkpoint")  # own saves stay open
    for domain, name in [("__save__default__bench-x", ""), ("default", "bench-claim")]:
        try:
            admin.block_bench_writes(plain, domain, name)
            raise AssertionError(f"non-admin write must 403 for {domain!r}/{name!r}")
        except HTTPException as exc:
            assert exc.status_code == 403
    print("  bench guard: bench saves/domains 403 for non-admins, open otherwise ✓")


def test_personal_saves_namespace():
    from app import saves

    uid = auth_store.user_uid("Alice")
    assert auth_store.user_uid("Alice") == uid and len(uid) == 8, "uid must be stable, 8 hex"
    # A rename must not orphan personal saves: the uid rides the record, not the name.
    auth_store.register("Renamee", "password-r")
    uid_r = auth_store.user_uid("Renamee")
    auth_store.rename_user("renamee", "Renamed")
    assert auth_store.user_uid("Renamed") == uid_r, "uid must survive a rename"

    mine = saves.personal_name(uid, "v1")
    assert saves.split_owner(mine) == (uid, "v1")
    assert saves.split_owner("plain-save") == (None, "plain-save")

    someone_else = saves.personal_name("deadbeef", "v1")
    orig_g, orig_lr = saves._graphiti_names, saves._lightrag_names
    saves._graphiti_names = lambda d: {mine, someone_else, "shared-x", "bench-q"}
    saves._lightrag_names = lambda d: {"shared-x", saves.personal_name(uid, "lr-only")}
    try:
        vis = {(e["name"], e["mine"]): sorted(e["engines"])
               for e in saves.visible_saves("default", uid)}
        assert vis[("v1", True)] == ["graphiti"]
        assert vis[("lr-only", True)] == ["lightrag"]
        assert vis[("shared-x", False)] == ["graphiti", "lightrag"]
        assert ("bench-q", False) in vis
        assert ("v1", False) not in vis, "another user's personal save must stay invisible"
        assert saves.resolve_stored("default", "v1", uid) == mine, "own copy wins"
        assert saves.resolve_stored("default", "shared-x", uid) == "shared-x"
        assert saves.resolve_stored("default", "v1", "00000000") == "v1", "no personal copy -> shared name"
    finally:
        saves._graphiti_names, saves._lightrag_names = orig_g, orig_lr
    print("  personal saves: uid rename-stable; visibility + resolution correct ✓")


TESTS = [
    test_first_account_bootstraps_admin,
    test_admin_users_env_override,
    test_grant_and_revoke,
    test_rename_carries_sessions_and_data,
    test_password_reset_revokes_sessions,
    test_delete_account_removes_everything,
    test_router_guards,
    test_default_admin_seeding,
    test_bench_write_guard,
    test_personal_saves_namespace,
]

if __name__ == "__main__":
    failed = 0
    print(f"running admin auth tests (state -> {_SCRATCH})…")
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ✗ {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
