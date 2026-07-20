"""Bench results local-archive tests — no network, no git:

    backend/.venv/bin/python tests/test_archive.py

The archive is the pull-proof copy of every finished run's report: gitignored,
add-only, on this machine. Covers: report json+md copied, same-run re-archive is
a clean overwrite, a missing run degrades to an error event (never a raised
exception), the archive dir is actually gitignored — and the record-redaction
that keeps key-shaped fragments out of anything that might later be committed.
"""

import os
import sys
import tempfile
from pathlib import Path

_SCRATCH = tempfile.mkdtemp(prefix="noema-archive-test-")
os.environ["NOEMA_STATE_DIR"] = _SCRATCH  # workdir AND archive both under scratch
os.environ.setdefault("OPENAI_API_KEY", "test-key-never-called")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.bench import archive, store  # noqa: E402


def test_archive_copies_and_overwrites():
    runs = store.work_dir("ds1") / "runs"
    runs.mkdir(parents=True)
    (runs / "r1.json").write_text('{"run": 1}')
    (runs / "r1.md").write_text("# report v1")

    ev = archive.save("ds1", "r1")
    assert ev["phase"] == "results_archived", ev
    dest = archive.ARCHIVE_DIR / "ds1"
    assert (dest / "r1.json").read_text() == '{"run": 1}'
    assert (dest / "r1.md").read_text() == "# report v1"

    (runs / "r1.md").write_text("# report v2 (rejudged)")
    ev = archive.save("ds1", "r1")
    assert ev["phase"] == "results_archived"
    assert (dest / "r1.md").read_text() == "# report v2 (rejudged)", "same id -> overwrite"
    print("  archive: json+md copied, re-archive overwrites cleanly ✓")


def test_missing_run_degrades_gracefully():
    ev = archive.save("ds1", "no-such-run")
    assert ev["phase"] == "results_archive_error" and "no report files" in ev["detail"]
    print("  archive: missing run -> error event, never an exception ✓")


def test_archive_dir_is_gitignored():
    import subprocess

    r = subprocess.run(
        ["git", "check-ignore", "tests/results/bench_archive/x/r.json"],
        cwd=str(REPO), capture_output=True, text=True)
    assert r.returncode == 0, "the archive path MUST be gitignored — that is the pull-proof guarantee"
    print("  archive: default location is gitignored — pulls can never touch it ✓")


def test_error_strings_are_redacted():
    from app.bench import scoring

    dirty = "Incorrect API key provided: sk-proj-AbC123xyz789 (request id req-1)"
    clean = scoring.redact(dirty)
    assert "sk-proj" not in clean and "[redacted]" in clean, clean
    assert scoring.redact("plain connection timeout") == "plain connection timeout"
    print("  redaction: key-shaped fragments never reach persisted records ✓")


TESTS = [
    test_archive_copies_and_overwrites,
    test_missing_run_degrades_gracefully,
    test_archive_dir_is_gitignored,
    test_error_strings_are_redacted,
]

if __name__ == "__main__":
    failed = 0
    print(f"running archive tests (state -> {_SCRATCH})…")
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
