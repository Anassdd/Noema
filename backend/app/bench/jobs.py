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
        # Progress derived from the event stream (see _track): current stage +
        # its fraction, plus a rate clock for the ETA. The clock restarts on every
        # stage change AND on resumed/skipped replays — replayed units arrive in
        # milliseconds and would otherwise make the ETA absurdly optimistic.
        self._stage = "starting"
        self._stage_done = 0
        self._stage_total = 0
        self._build_seen = False
        self._questions = 0
        self._n_configs = 1
        self._answered = 0
        self._rate_t0 = time.time()
        self._rate_f0 = 0.0

    def append(self, ev: dict) -> None:
        self._track(ev)
        self.events.append(ev)
        self._changed.set()

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ---- progress + ETA ---------------------------------------------------------
    def _frac(self) -> float:
        return (self._stage_done / self._stage_total) if self._stage_total else 0.0

    def _reset_rate(self) -> None:
        self._rate_t0 = time.time()
        self._rate_f0 = self._frac()

    def _set_stage(self, stage: str, done: int, total: int) -> None:
        changed = stage != self._stage
        self._stage, self._stage_done, self._stage_total = stage, done, total
        if changed:
            self._reset_rate()

    def _track(self, ev: dict) -> None:
        p = ev.get("phase")
        if p == "start":
            if ev.get("rejudge"):
                self._set_stage("judging", 0, ev.get("records") or 0)
            else:
                self._questions = ev.get("questions") or 0
                cfgs = ev.get("configs")
                self._n_configs = len(cfgs) if isinstance(cfgs, list) and cfgs else 1
        elif p in ("build_start", "lightrag_build_start"):
            self._build_seen = True
            self._set_stage("building", 0, 0)
        elif p in ("rag_doc", "lightrag_doc"):
            self._build_seen = True
            self._set_stage("building", ev.get("i") or 0, ev.get("total") or 0)
            if ev.get("skipped"):
                self._reset_rate()
        elif p == "graph_episode":
            self._build_seen = True
            self._set_stage("building", ev.get("doc_i") or 0, ev.get("docs") or 0)
        elif p == "answered":
            self._answered += 1
            self._set_stage("answering", self._answered,
                            self._questions * self._n_configs)
            if ev.get("resumed"):
                self._reset_rate()
        elif p == "judge_start":
            self._set_stage("judging", 0, ev.get("verdicts") or 0)
        elif p == "scored":
            self._set_stage("judging", ev.get("i") or 0, ev.get("total") or 0)
        elif p in ("done", "report"):
            self._set_stage("finished", 1, 1)

    _WEIGHTS_BUILD = (("building", 0.35), ("answering", 0.5), ("judging", 0.15))
    _WEIGHTS_NO_BUILD = (("answering", 0.8), ("judging", 0.2))

    def _overall_pct(self) -> float:
        if self._stage == "finished":
            return 1.0
        weights = self._WEIGHTS_BUILD if self._build_seen else self._WEIGHTS_NO_BUILD
        if self.kind == "rejudge":
            weights = (("judging", 1.0),)
        pct = 0.0
        for stage, w in weights:
            if stage == self._stage:
                return pct + w * self._frac()
            pct += w  # stages before the current one count as complete
        return 0.0

    def _eta_seconds(self) -> int | None:
        """Remaining time for the CURRENT stage, extrapolated from its own measured
        rate — only once enough of it ran to trust (>=20s and >=2% real progress)."""
        if self._stage not in ("building", "answering", "judging") or not self._stage_total:
            return None
        elapsed = time.time() - self._rate_t0
        gained = self._frac() - self._rate_f0
        if elapsed < 20 or gained < 0.02:
            return None
        rate = gained / elapsed
        return max(0, round((1.0 - self._frac()) / rate))

    def info(self) -> dict:
        return {"job_id": self.job_id, "dataset": self.dataset, "kind": self.kind,
                "started_at": self.started_at, "done": self.done, "events": len(self.events),
                "progress": {"stage": self._stage, "done": self._stage_done,
                             "total": self._stage_total, "pct": round(self._overall_pct(), 4),
                             "eta_seconds": self._eta_seconds()}}

    async def tail(self, since: int = 0) -> AsyncIterator[dict]:
        """Replay events from `since`, then follow live until the job finishes.
        Purely an observer — cancelling a tail never touches the job. While the
        job is quiet (a long build episode, a slow provider) a `ping` is yielded
        every few seconds: corporate proxies/AV buffer chunked responses until
        bytes flow, and an idle stream otherwise looks frozen to the tab."""
        i = max(0, since)
        while True:
            while i < len(self.events):
                yield self.events[i]
                i += 1
            if self.done:
                return
            self._changed.clear()
            try:
                await asyncio.wait_for(self._changed.wait(), timeout=8)
            except asyncio.TimeoutError:
                yield {"phase": "ping"}


_jobs: dict[str, BenchJob] = {}


def get(job_id: str) -> BenchJob | None:
    return _jobs.get(job_id)


def active_for(dataset: str) -> BenchJob | None:
    """The dataset's running job, if any (at most one — see start())."""
    return next((j for j in reversed(_jobs.values())
                 if j.dataset == dataset and not j.done), None)


def latest_for(dataset: str) -> BenchJob | None:
    return next((j for j in reversed(_jobs.values()) if j.dataset == dataset), None)


def all_active() -> list[BenchJob]:
    """Every dataset's running job — the overnight view. Jobs are per dataset
    (one each), so several datasets happily run at once."""
    return [j for j in _jobs.values() if not j.done]


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
