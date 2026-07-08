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

_REPO = Path(__file__).resolve().parents[3]
RAW_DIR = Path(os.getenv("BENCH_DATA_DIR", "") or _REPO / "backend" / "data" / "bench")
WORK_DIR = Path(os.getenv("BENCH_WORK_DIR", "") or _REPO / "tests" / "results" / "bench")


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
