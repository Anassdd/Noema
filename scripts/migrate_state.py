"""Move all runtime state under one root (STORAGE.md §3) — safely.

    python scripts/migrate_state.py --state-dir backend/var           # preview
    python scripts/migrate_state.py --state-dir backend/var --apply   # move + verify

Moves each store from its historical location to <state-dir>/<name>, verifies file
counts and byte totals afterwards, and NEVER deletes anything. Refuses to run while
the backend holds the stores open (FalkorDB answering on its port = server running).
Finish by adding NOEMA_STATE_DIR=<state-dir> to backend/.env and running `make test`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# (state subdir, historical location) — mirrors app.config.state_path call sites.
MOVES = [
    ("chroma", REPO / "backend" / ".chroma"),
    ("falkor", REPO / "tests" / "results" / "graph_store"),
    ("lightrag", REPO / "backend" / "data" / "lightrag"),
    ("textgraph", REPO / "backend" / "app" / "textgraph_store"),
    ("schemas", REPO / "tests" / "results" / "graph_schemas"),
    ("bench", REPO / "tests" / "results" / "bench"),
    ("auth", REPO / "backend" / "data" / "auth"),
    ("memory", REPO / "backend" / "data" / "memory"),
]
FILE_MOVES = [
    ("conversations", REPO / "backend" / "app" / "conversations.db"),
]
BELIEFS = ("beliefs", REPO / "backend" / ".beliefs")


def _measure(path: Path) -> tuple[int, int]:
    if path.is_file():
        return 1, path.stat().st_size
    files = [p for p in path.rglob("*") if p.is_file()]
    return len(files), sum(p.stat().st_size for p in files)


def _server_running() -> bool:
    port = int(os.getenv("FALKOR_PORT", "6399"))
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--apply", action="store_true", help="actually move (default: preview)")
    args = ap.parse_args()
    root = (REPO / args.state_dir).resolve() if not Path(args.state_dir).is_absolute() \
        else Path(args.state_dir)

    if args.apply and _server_running():
        print("✗ FalkorDB is answering — the backend looks RUNNING. Stop it first "
              "(open file handles make a live move unsafe).")
        return 1

    pending = []
    for sub, legacy in MOVES + FILE_MOVES + [BELIEFS]:
        if not legacy.exists():
            continue
        target = root / sub / legacy.name if (sub, legacy) in FILE_MOVES else root / sub
        if target.exists():
            print(f"= {sub:<14} target already exists, skipped ({target})")
            continue
        pending.append((sub, legacy, target))

    if not pending:
        print("Nothing to migrate — either already done or no state yet.")
        return 0

    for sub, legacy, target in pending:
        n, size = _measure(legacy)
        print(f"{'→' if args.apply else '·'} {sub:<14} {legacy}  →  {target}"
              f"   ({n} files, {size / 1e6:.1f} MB)")
        if args.apply:
            before = (n, size)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(legacy), str(target))
            after = _measure(target)
            if after != before:
                print(f"✗ VERIFY FAILED for {sub}: {before} -> {after} — investigate "
                      "before starting the backend.")
                return 1

    if args.apply:
        print(f"\n✓ moved + verified. Now add to backend/.env:\n    NOEMA_STATE_DIR={args.state_dir}"
              "\nthen restart the backend and run `make test`.")
    else:
        print("\nPreview only — nothing moved. Re-run with --apply (backend stopped).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
