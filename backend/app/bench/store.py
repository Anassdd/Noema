"""Bench filesystem layout + manifest/gold/run IO. Everything the bench persists
lives under two roots:

    RAW_DIR   backend/data/bench/*.jsonl      the datasets you drop in (gitignored)
    WORK_DIR  tests/results/bench/<dataset>/  prepared corpus, gold questions,
                                              manifest, runs — the durable artifacts

The gold questions and reports are meant to be committed (they ARE the frozen test
set); the prepared corpus and raw data are reproducible, so they stay out of git.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from app.config import state_path

_REPO = Path(__file__).resolve().parents[3]


def sibling(sub: str, legacy: Path) -> Path:
    """The zero-config link between the code and data repos: when a
    `noema-bench-data` clone sits BESIDE this repo, its `<sub>` dir is the
    default home for that store — same convention on every machine (Mac +
    GitHub, machine de dev + GitLab), nothing in .env. Override the location
    with BENCH_SIBLING_DIR (empty string disables the convention entirely —
    tests use that). Explicit per-store env vars and NOEMA_STATE_DIR still
    win over this default."""
    root = os.getenv("BENCH_SIBLING_DIR")
    if root is None:
        root = str(_REPO.parent / "noema-bench-data")
    if root and Path(root).is_dir():
        return Path(root) / sub
    return legacy


RAW_DIR = Path(os.getenv("BENCH_DATA_DIR", "")
               or sibling("datasets", _REPO / "backend" / "data" / "bench"))
WORK_DIR = Path(os.getenv("BENCH_WORK_DIR", "")
                or state_path("bench",
                              sibling("work", _REPO / "tests" / "results" / "bench")))


def work_dir(dataset: str) -> Path:
    d = WORK_DIR / dataset
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


# ---- manifest: what has been prepared/built for a dataset --------------------

def load_manifest(dataset: str) -> dict:
    return _read_json(work_dir(dataset) / "manifest.json", {"dataset": dataset, "builds": []})


def save_manifest(dataset: str, manifest: dict) -> None:
    _write_json(work_dir(dataset) / "manifest.json", manifest)


def find_build(manifest: dict, fingerprint: str) -> dict | None:
    return next((b for b in manifest.get("builds", []) if b.get("fingerprint") == fingerprint), None)


# ---- prepared corpus ----------------------------------------------------------

def load_corpus(dataset: str) -> list[dict]:
    """[{id, text, tokens, truncated}] — written by datasets.prepare()."""
    return _read_json(work_dir(dataset) / "corpus.json", [])


def save_corpus(dataset: str, docs: list[dict]) -> None:
    _write_json(work_dir(dataset) / "corpus.json", docs)


# ---- gold questions ------------------------------------------------------------

def load_gold(dataset: str) -> list[dict]:
    """[{id, question, answer, evidence, type, status}] — status: draft|approved."""
    return _read_json(work_dir(dataset) / "gold.json", [])


def save_gold(dataset: str, questions: list[dict]) -> None:
    _write_json(work_dir(dataset) / "gold.json", questions)


# ---- runs -----------------------------------------------------------------------

def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def save_run(dataset: str, run_id: str, report: dict, markdown: str) -> None:
    runs = work_dir(dataset) / "runs"
    _write_json(runs / f"{run_id}.json", report)
    (runs / f"{run_id}.md").write_text(markdown, encoding="utf-8")


def load_run(dataset: str, run_id: str) -> dict | None:
    return _read_json(work_dir(dataset) / "runs" / f"{run_id}.json", None)


def find_run_records(dataset: str, resume_key: str) -> list[dict] | None:
    """The newest finished run whose answer identity (build + configs + answer model +
    scope + gold) matches `resume_key` — its records let a re-run with only the JUDGE
    changed reuse every paid answer and re-pay verdicts only. Runs from before the
    key was stamped into reports simply never match."""
    runs = work_dir(dataset) / "runs"
    if not runs.exists():
        return None
    for f in sorted(runs.glob("*.json"), reverse=True):
        run = _read_json(f, None)
        if run and run.get("resume_key") == resume_key and run.get("records"):
            return run["records"]
    return None


def delete_run(dataset: str, run_id: str) -> bool:
    """Remove one run's report (json + md) from the workdir. The archive copy in
    bench_archive/ is deliberately NOT touched — it is the keep-everything safety
    net, so a UI delete can never destroy the last record of a paid run."""
    runs = work_dir(dataset) / "runs"
    found = False
    for suffix in (".json", ".md"):
        f = runs / f"{run_id}{suffix}"
        if f.exists():
            f.unlink()
            found = True
    return found


# ---- in-flight query records (crash-safe resume of the ANSWER phase) -----------
# The query phase can run for hours; persisting records only at the end means a crash
# or a disconnect at question 900/1000 re-pays everything. Each answered record is
# appended here as one JSON line, keyed by a resume_key derived from the run's identity
# (build fingerprint + configs + answer model + scope + gold content) so a re-launched
# identical run finds its own partial and skips what it already answered. Deleted once
# the final report is written.

def _inflight_path(dataset: str, resume_key: str) -> Path:
    d = work_dir(dataset) / "runs" / "inflight"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{resume_key}.jsonl"


def append_record(dataset: str, resume_key: str, rec: dict) -> None:
    with _inflight_path(dataset, resume_key).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_records(dataset: str, resume_key: str) -> list[dict]:
    path = _inflight_path(dataset, resume_key)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn final line from a hard crash — skip it, keep the rest
    return out


def clear_inflight(dataset: str, resume_key: str) -> None:
    _inflight_path(dataset, resume_key).unlink(missing_ok=True)


def clear_all_inflight(dataset: str) -> int:
    """Discard every partial answer log for a dataset (the KILL path: the next run
    starts from question 1). Finished runs, builds and the archive are untouched.
    Returns how many partial logs were dropped."""
    d = work_dir(dataset) / "runs" / "inflight"
    if not d.exists():
        return 0
    files = list(d.glob("*.jsonl"))
    for f in files:
        f.unlink(missing_ok=True)
    return len(files)


def load_run_markdown(dataset: str, run_id: str) -> str | None:
    path = work_dir(dataset) / "runs" / f"{run_id}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


def list_runs(dataset: str) -> list[dict]:
    """Newest first: [{run_id, at, configs, headline}] — light index read from each report."""
    runs = work_dir(dataset) / "runs"
    if not runs.exists():
        return []
    out = []
    for f in sorted(runs.glob("*.json"), reverse=True):
        r = _read_json(f, None)
        if r:
            out.append({
                "run_id": r.get("run_id", f.stem),
                "at": r.get("at"),
                "configs": [row.get("config") for row in r.get("headline", [])],
                "fingerprint": r.get("build", {}).get("fingerprint"),
            })
    return out
