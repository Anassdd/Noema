"""Detached bench-job tests — no network, no LLM (fake event generators):

    backend/.venv/bin/python tests/test_bench_jobs.py

Covers the money-safety contract: a job keeps running with NO consumer attached
(the closed-tab case), tails replay the full log and can reattach mid-run, only
one job runs per dataset, stop() cancels cleanly with a 'stopped' event, and a
crashing generator becomes an 'error' event instead of a silent death.
"""

import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.bench import jobs  # noqa: E402


async def _events(n=3, delay=0.01, fail_at=None):
    for i in range(n):
        await asyncio.sleep(delay)
        if fail_at == i:
            raise RuntimeError("provider exploded")
        yield {"phase": "answered", "i": i}
    yield {"phase": "done"}


def test_job_survives_without_consumer():
    async def main():
        job = jobs.start("ds-a", "run", _events())
        # nobody tails it — the closed-tab case — yet the work completes
        await job._task
        assert job.done
        assert [e["phase"] for e in job.events] == ["job", "answered", "answered", "answered", "done"]
    asyncio.run(main())
    print("  detached: job finished with no consumer attached ✓")


def test_tail_replays_and_reattaches():
    async def main():
        job = jobs.start("ds-b", "run", _events(n=4))
        first = []
        async for ev in job.tail():
            first.append(ev)
            if len(first) == 2:
                break  # simulate the tab closing mid-run
        await job._task  # the job never noticed
        second = [ev async for ev in job.tail(0)]  # reopened page replays everything
        assert len(second) == 6 and second[0]["phase"] == "job" and second[-1]["phase"] == "done"
        resumed = [ev async for ev in job.tail(len(first))]  # or just the missed part
        assert len(resumed) == 6 - len(first)
    asyncio.run(main())
    print("  reattach: broken tail ignored, full + partial replays correct ✓")


def test_single_job_per_dataset():
    async def main():
        job = jobs.start("ds-c", "run", _events(n=2, delay=0.05))
        assert jobs.start("ds-c", "run", _events()) is None, "second job must be refused"
        assert jobs.active_for("ds-c") is job
        await job._task
        assert jobs.active_for("ds-c") is None
        assert jobs.start("ds-c", "run", _events()) is not None, "done job must not block"
    asyncio.run(main())
    print("  exclusivity: one running job per dataset, freed on completion ✓")


def test_stop_yields_stopped_event():
    async def main():
        job = jobs.start("ds-d", "run", _events(n=50, delay=0.02))
        await asyncio.sleep(0.05)
        job.stop()
        events = [ev async for ev in job.tail()]
        assert events[-1]["phase"] == "stopped" and "saved" in events[-1]["detail"]
        assert job.done
    asyncio.run(main())
    print("  stop: cancelled job ends with a 'stopped' event, log intact ✓")


def test_crash_becomes_error_event():
    async def main():
        job = jobs.start("ds-e", "run", _events(n=5, fail_at=2))
        events = [ev async for ev in job.tail()]
        assert events[-1]["phase"] == "error" and "saved" in events[-1]["detail"]
        assert "provider exploded" in events[-1]["detail"]
        assert job.done
    asyncio.run(main())
    print("  crash: generator exception -> error event, never a silent death ✓")


def test_multiple_datasets_run_concurrently():
    """The overnight contract: one job per dataset, but datasets in PARALLEL —
    all_active sees them all, tails are independent, stopping one never touches
    the other."""
    async def main():
        a = jobs.start("night-a", "run", _events(n=30, delay=0.02))
        b = jobs.start("night-b", "run", _events(n=30, delay=0.02))
        assert a is not None and b is not None, "two datasets must both start"
        await asyncio.sleep(0.05)
        active = {j.dataset for j in jobs.all_active()}
        assert {"night-a", "night-b"} <= active, f"both must show as running: {active}"

        a.stop()
        events_a = [ev async for ev in a.tail()]
        assert events_a[-1]["phase"] == "stopped", "stopped job ends with the pause event"
        assert jobs.active_for("night-b") is b and not b.done, \
            "stopping one dataset must not touch the other"
        events_b = [ev async for ev in b.tail()]
        assert len(events_b) > 10, "the surviving job must have kept producing"
        assert b.done and not jobs.all_active(), "everything drained -> nothing active"
    asyncio.run(main())
    print("  concurrency: two datasets run + tail + stop independently; all_active tracks them ✓")


def test_progress_tracks_stages():
    """The dataset list's ring: progress follows the event stream through
    answering -> judging -> finished, the overall pct only ever grows, and
    the answer total is questions x configs from the start event."""
    job = jobs.BenchJob("ds-p", "run")
    seen = []

    def feed(ev):
        job.append(ev)
        seen.append(dict(job.info()["progress"]))

    feed({"phase": "start", "questions": 4, "configs": ["rag", "graph"]})
    for i in range(4):
        feed({"phase": "answered", "config": "rag", "i": i + 1, "total": 4,
              "resumed": i == 0})
    for i in range(4):
        feed({"phase": "answered", "config": "graph", "i": i + 1, "total": 4})
    feed({"phase": "judge_start", "verdicts": 8})
    for i in range(8):
        feed({"phase": "scored", "i": i + 1, "total": 8})
    feed({"phase": "done"})

    pr = job.info()["progress"]
    assert pr["stage"] == "finished" and pr["pct"] == 1.0
    stages = [p["stage"] for p in seen]
    assert "answering" in stages and "judging" in stages
    pcts = [p["pct"] for p in seen]
    assert all(b >= a - 1e-9 for a, b in zip(pcts, pcts[1:])), "pct must never go backwards"
    mid = next(p for p in seen if p["stage"] == "answering" and p["done"] == 8)
    assert mid["total"] == 8, "total = questions x configs"
    assert seen[0]["eta_seconds"] is None, "no ETA before real progress is measurable"
    print("  progress: stages tracked, pct monotonic, totals from start event ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running bench-job tests…")
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
