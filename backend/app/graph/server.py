"""Run the FalkorDB server that ships *inside* falkordblite as a single shared local
process — embedded-like convenience (no Docker, no install) with server reliability.

Why not the pure-embedded driver: graphiti fires many concurrent connections during
extraction, and redislite's embedded mode spins an ephemeral server per connection, so
writes scatter and never converge. One shared server (this) fixes that. It's the same
binary a real deployment uses — so "local now, server later" is a host/port change.

Auto-started on demand and stopped at process exit. Idempotent: if the port already
answers, it's reused.
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import time
from pathlib import Path

_proc: subprocess.Popen | None = None


def _bundled_binaries() -> tuple[Path, Path]:
    import redislite
    base = Path(os.path.dirname(redislite.__file__)) / "bin"
    return base / "redis-server", base / "falkordb.so"


def _responding(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_local_server(host: str = "127.0.0.1", port: int = 6399,
                        db_dir: str | Path = ".", *, wait: float = 15.0) -> tuple[str, int]:
    """Start (once) the bundled FalkorDB server, persisting to db_dir/falkor.rdb."""
    global _proc
    if _responding(host, port):
        return host, port

    server, module = _bundled_binaries()
    if not server.exists() or not module.exists():
        raise RuntimeError("Bundled FalkorDB server not found — install "
                           "graphiti-core[falkordblite] in this venv.")
    Path(db_dir).mkdir(parents=True, exist_ok=True)
    _proc = subprocess.Popen(
        [str(server), "--bind", host, "--port", str(port),
         "--loadmodule", str(module), "--dir", str(db_dir),
         "--dbfilename", "falkor.rdb", "--save", "60", "1", "--appendonly", "no"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    atexit.register(stop_local_server)

    deadline = time.time() + wait
    while time.time() < deadline:
        if _proc.poll() is not None:
            raise RuntimeError(f"FalkorDB server exited early (code {_proc.returncode}).")
        if _responding(host, port):
            return host, port
        time.sleep(0.15)
    raise RuntimeError(f"FalkorDB server did not come up on {host}:{port} within {wait}s.")


def stop_local_server():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=3)
        except Exception:
            _proc.kill()
    _proc = None


# ---- raw graph admin (sync client, run in a thread by async callers) ---------
def falkor_ops(fn):
    """Run one operation against the FalkorDB server with a short-lived sync client.
    The shared helper behind whole-graph admin: saves, Dream checkpoints."""
    from falkordb import FalkorDB

    from app.graph.config import graph_config

    db = FalkorDB(host=graph_config.host, port=graph_config.port)
    try:
        return fn(db)
    finally:
        try:
            db.close()
        except Exception:
            pass


def list_graphs() -> list[str]:
    return falkor_ops(lambda db: db.list_graphs())


def copy_graph(src: str, dest: str) -> None:
    """Full copy via GRAPH.COPY, overwriting any existing dest."""
    def _do(db):
        if dest in db.list_graphs():
            db.select_graph(dest).delete()
        db.select_graph(src).copy(dest)

    falkor_ops(_do)


def drop_graph(name: str) -> None:
    def _do(db):
        if name in db.list_graphs():
            db.select_graph(name).delete()

    falkor_ops(_do)
