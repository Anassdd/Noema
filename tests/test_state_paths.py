"""State-root seam tests — no network (fresh subprocesses, real path resolution):

    backend/.venv/bin/python tests/test_state_paths.py

The contract: with NOEMA_STATE_DIR unset every store resolves to its HISTORICAL
location (byte-identical behavior — the guarantee that adopting the seam changed
nothing); with it set, every store resolves under the one root; explicit per-store
env vars still win over the root.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"

_PROBE = """
import json
from pathlib import Path
from app.bench import store as bench_store
from app.graph import config as graph_config
from app.graph import schema as graph_schema
from app import auth_store, beliefs, conversation_store, memory_store
from app.config import settings
from app.retrieval import store as retrieval_store
from app.textgraph import store as textgraph_store
print(json.dumps({
    "chroma": settings.vector_dir or str(retrieval_store._DEFAULT_DIR),
    "falkor": graph_config.load_graph_config().db_dir,
    "schemas": str(graph_schema._SCHEMA_DIR),
    "bench": str(bench_store.WORK_DIR),
    "auth": str(auth_store._AUTH_DIR),
    "memory": str(memory_store._DIR),
    "conversations": str(conversation_store._DB_PATH),
    "beliefs": str(beliefs._DIR),
    "textgraph": str(textgraph_store.STORE_DIR),
}))
"""


def _resolve(extra_env: dict) -> dict:
    env = {**os.environ, **extra_env}
    env.pop("NOEMA_STATE_DIR", None)
    # This suite tests the NOEMA_STATE_DIR seam in isolation: blank the per-store
    # overrides a developer .env sets (e.g. the noema-bench-data repo paths) —
    # their precedence has its own test.
    for k in ("BENCH_DATA_DIR", "BENCH_WORK_DIR", "BENCH_ARCHIVE_DIR",
              "BENCH_SIBLING_DIR"):
        env[k] = ""
    env.update({k: v for k, v in extra_env.items()})
    r = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,
                       cwd=BACKEND, env=env)
    assert r.returncode == 0, r.stderr[-1500:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_unset_means_historical_paths():
    p = _resolve({})
    expected = {
        "chroma": BACKEND / ".chroma",
        "falkor": REPO / "tests" / "results" / "graph_store",
        "schemas": REPO / "tests" / "results" / "graph_schemas",
        "bench": REPO / "tests" / "results" / "bench",
        "auth": BACKEND / "data" / "auth",
        "memory": BACKEND / "data" / "memory",
        "conversations": BACKEND / "app" / "conversations.db",
        "beliefs": BACKEND / ".beliefs",
        "textgraph": BACKEND / "app" / "textgraph_store",
    }
    for key, want in expected.items():
        assert p[key] == str(want), f"{key}: {p[key]} != {want} — legacy default drifted!"
    print(f"  legacy: all {len(expected)} stores at their historical paths ✓")


def test_state_dir_consolidates_everything():
    root = "/tmp/noema-state-test"
    p = _resolve({"NOEMA_STATE_DIR": root})
    for key, path in p.items():
        assert path.startswith(root + "/"), f"{key} escaped the state root: {path}"
    assert p["falkor"] == f"{root}/falkor" and p["conversations"] == f"{root}/conversations/conversations.db"
    print(f"  state root: all {len(p)} stores under {root} ✓")


def test_explicit_override_beats_root():
    p = _resolve({"NOEMA_STATE_DIR": "/tmp/noema-state-test",
                  "VECTOR_DIR": "/tmp/elsewhere-chroma",
                  "BENCH_WORK_DIR": "/tmp/elsewhere-bench"})
    assert p["chroma"] == "/tmp/elsewhere-chroma", "VECTOR_DIR must win over the root"
    assert p["bench"] == "/tmp/elsewhere-bench", "BENCH_WORK_DIR must win over the root"
    assert p["falkor"].startswith("/tmp/noema-state-test/"), "non-overridden stores follow the root"
    print("  precedence: explicit env var > state root > legacy ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running state-path tests…")
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
