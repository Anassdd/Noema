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
