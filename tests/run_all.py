"""Run every free test suite — the one entry point (`make test`; any future CI too):

    backend/.venv/bin/python tests/run_all.py

Discovers tests/test_*.py and runs each in its own process (the suites are
script-style and isolated on purpose — they work offline with zero test-framework
dependencies, which the locked-down prod machine requires). Suites that spend money
are excluded explicitly, never by accident.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# These make REAL LLM calls (a few cents each) and need a live provider key.
# Run them deliberately, one at a time — never from `make test`.
PAID = {"test_graph.py"}


def main() -> int:
    suites = sorted(p for p in TESTS_DIR.glob("test_*.py") if p.name not in PAID)
    failed: list[str] = []
    t0 = time.perf_counter()
    for suite in suites:
        r = subprocess.run([sys.executable, str(suite)], capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        mark = "✓" if r.returncode == 0 else "✗"
        print(f"{mark} {suite.name:<28} {tail}")
        if r.returncode != 0:
            failed.append(suite.name)
            print(r.stdout[-2000:], r.stderr[-2000:], sep="\n")
    print(f"\n{len(suites) - len(failed)}/{len(suites)} suites passed "
          f"in {time.perf_counter() - t0:.0f}s"
          + (f" — FAILED: {', '.join(failed)}" if failed else ""))
    print(f"(excluded paid suites: {', '.join(sorted(PAID))})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
