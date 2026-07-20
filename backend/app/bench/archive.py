"""Local results archive — every finished run is copied to a gitignored folder.

The workdir (runs, reports, manifest) is git-TRACKED, so a `git pull` could in
principle collide with it. The archive is the pull-proof copy on the dev machine:
`tests/results/bench_archive/<dataset>/` is gitignored, which means a pull only
ever ADDS content elsewhere in the repo and can never replace or conflict with
what sits here. Nothing is committed or pushed automatically — publishing results
to git stays a deliberate, manual act.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.bench import store
from app.config import state_path

_REPO = Path(__file__).resolve().parents[3]
ARCHIVE_DIR = state_path("bench_archive",
                         _REPO / "tests" / "results" / "bench_archive")


def save(dataset: str, run_id: str) -> dict:
    """Copy the run's report (JSON + markdown) into the archive. Returns ONE event
    dict for the job log and never raises — archiving is aftercare, not part of
    the run. Same run id re-archived = same files overwritten (identical content)."""
    try:
        src = store.work_dir(dataset) / "runs"
        dest = ARCHIVE_DIR / dataset
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for suffix in (".json", ".md"):
            f = src / f"{run_id}{suffix}"
            if f.exists():
                shutil.copy2(f, dest / f.name)
                copied.append(f.name)
        if not copied:
            return {"phase": "results_archive_error",
                    "detail": f"no report files found for run {run_id}"}
        return {"phase": "results_archived",
                "detail": f"report copied to {dest} ({', '.join(copied)}) — "
                          "gitignored, pulls can never touch it"}
    except Exception as exc:  # noqa: BLE001 — aftercare must never kill a finished run
        return {"phase": "results_archive_error", "detail": str(exc)[:200]}
