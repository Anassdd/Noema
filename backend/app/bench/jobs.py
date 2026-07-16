"""Detached bench jobs — a run outlives the browser tab that started it.

The run/rejudge generators used to be driven by the HTTP response: closing the tab
made uvicorn cancel the generator mid-question. Nothing paid was lost (episodes,
answers and verdicts persist as they happen) but the run STOPPED and had to be
resumed by hand. A job instead drives the generator as an asyncio.Task owned by the
server; HTTP responses merely TAIL its event log. Closing the tab kills the tail,
never the work — reopening the page finds the active job and reattaches from the
first event.

In-memory by design: a server restart kills the task, and the existing resume
machinery (build episodes, per-answer records, per-verdict persistence) picks up on
the next Run with nothing re-paid.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator

_KEEP_DONE = 3  # finished jobs kept per dataset (for late reattaches), older pruned


class BenchJob:
    def __init__(self, dataset: str, kind: str):
        self.job_id = uuid.uuid4().hex[:12]
        self.dataset = dataset
        self.kind = kind  # "run" | "rejudge"
        self.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self.events: list[dict] = []
        self.done = False
        self._changed = asyncio.Event()
        self._task: asyncio.Task | None = None

    def append(self, ev: dict) -> None:
        self.events.append(ev)
        self._changed.set()

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    def info(self) -> dict:
        return {"job_id": self.job_id, "dataset": self.dataset, "kind": self.kind,
                "started_at": self.started_at, "done": self.done, "events": len(self.events)}

    async def tail(self, since: int = 0) -> AsyncIterator[dict]:
        """Replay events from `since`, then follow live until the job finishes.
        Purely an observer — cancelling a tail never touches the job."""
        i = max(0, since)
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.done:
                return
            self._changed.clear()
            await self._changed.wait()


_jobs: dict[str, BenchJob] = {}


def get(job_id: str) -> BenchJob | None:
    return _jobs.get(job_id)


def active_for(dataset: str) -> BenchJob | None:
    """The dataset's running job, if any (at most one — see start())."""
    return next((j for j in reversed(_jobs.values())
                 if j.dataset == dataset and not j.done), None)


def latest_for(dataset: str) -> BenchJob | None:
    return next((j for j in reversed(_jobs.values()) if j.dataset == dataset), None)


def _prune(dataset: str) -> None:
    done = [j for j in _jobs.values() if j.dataset == dataset and j.done]
    for j in done[:-_KEEP_DONE]:
        _jobs.pop(j.job_id, None)


async def _drive(job: BenchJob, agen: AsyncIterator[dict]) -> None:
    try:
        async for ev in agen:
            job.append(ev)
    except asyncio.CancelledError:
        job.append({"phase": "stopped",
                    "detail": "paused — everything built, answered and judged so far "
                              "is saved; press Run to resume from exactly here"})
    except Exception as exc:  # noqa: BLE001 — a bug must never eat the paid work silently
        job.append({"phase": "error",
                    "detail": f"{exc} — everything so far is saved; press Run to resume."})
    finally:
        job.done = True
        job._changed.set()


def start(dataset: str, kind: str, agen: AsyncIterator[dict]) -> BenchJob | None:
    """Launch `agen` as a detached job. Returns None when the dataset already has a
    job running — a second run would double-build and double-pay."""
    if active_for(dataset):
        return None
    _prune(dataset)
    job = BenchJob(dataset, kind)
    job.append({"phase": "job", "job_id": job.job_id, "kind": kind,
                "started_at": job.started_at})
    job._task = asyncio.get_running_loop().create_task(_drive(job, agen))
    _jobs[job.job_id] = job
    return job
