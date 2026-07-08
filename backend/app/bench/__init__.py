"""Bench package — run memory methods against fixed datasets and produce a report.

The flow (all driven from the Bench page, ?view=bench):

    raw jsonl (backend/data/bench/) -> prepare: unique contexts, capped corpus
    -> gold questions (drafted by LLM, edited/approved in the page)
    -> build ONCE per (corpus, cap, models) fingerprint — directly INTO a save of
       the default domain, so the built graph shows up in the graph page's Saves
    -> run configs (closed_book / rag / graph / hybrid) over the approved questions
    -> score (EM/F1, evidence recall, cross-family LLM judge) -> report (JSON + MD)

Public API: see datasets, goldgen, runner, report modules.
"""

from app.bench.datasets import dataset_status, list_datasets, prepare
from app.bench.runner import run_bench
from app.bench.store import load_gold, load_manifest, load_run, list_runs, save_gold

__all__ = [
    "list_datasets", "dataset_status", "prepare",
    "run_bench", "load_gold", "save_gold", "load_manifest", "load_run", "list_runs",
]
