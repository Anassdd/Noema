"""LIVE memory-judge eval — real LLM calls, run it yourself (costs ~10 small
calls on the configured chat model, a few cents):

    backend/.venv/bin/python tests/eval_memory_live.py

The no-network suite (test_memory_evolution.py) proves the MACHINERY: ops
apply, walls hold, nothing is lost. This one measures the JUDGE — does the
live model actually produce the right operations on realistic exchanges?
Pure LLM in/out: nothing here touches the memory files on disk.

Scenario set (one line each in the report):
  until      "in Paris until September 1st"  -> a now-add carrying 2026-09-01
  retire     "I passed the CFA exam!"        -> the CFA now-fact retires
  reversal   "actually the floors are fine"  -> the note REPLACES, not piles
  style      saved facts don't start with "The user"
  weave      /remember placement lands the fact in a sensible section
  past       rewrite_past turns "In Paris…" into past tense
  expand     "the turkish trip" expands to istanbul/turkey keywords
  journal    a tiny conversation summarizes to one compact line
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import memory_judge  # noqa: E402

TODAY = "2026-07-22"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail and not ok else ""))


def eval_until_and_style():
    ops = memory_judge.evolve(
        [{"role": "user", "content":
          "btw I'm in Paris until September 1st for my internship at BNP"},
         {"role": "assistant", "content": "Noted — enjoy Paris!"}],
        "", [], TODAY)
    added = ops["add"] + [(t, None) for t, _x in ops["profile"]]
    check("until", any(u == "2026-09-01" for _f, u in ops["add"]),
          f"adds={ops['add']} profile={ops['profile']}")
    texts = [f for f, _u in ops["add"]] + [t for _s, t in ops["profile"]]
    check("style", texts and not any(t.lower().startswith("the user") for t in texts),
          f"texts={texts}")


def eval_retire():
    ops = memory_judge.evolve(
        [{"role": "user", "content": "great news — I passed the CFA exam last week!"},
         {"role": "assistant", "content": "Congratulations!"}],
        "", ["Preparing the CFA exam. (2026-06-01)"], TODAY)
    check("retire", bool(ops["retire"]) or bool(ops["archive"]),
          f"retire={ops['retire']} archive={ops['archive']} ops={ops}")


def eval_note_reversal():
    ops = memory_judge.evolve(
        [{"role": "user", "content":
          "you know what, thinking about it more, the output floors are actually fine"},
         {"role": "assistant", "content": "Understood."}],
        "", [], TODAY,
        notes=["Basel output floors are too strict. (2026-07-01)"])
    check("reversal",
          any(rep is not None for _n, rep in ops["beliefs"]),
          f"beliefs={ops['beliefs']}")


def eval_weave():
    placed = memory_judge.place_fact(
        "prefers answers in French when discussing regulation",
        "## Work (2026-07-01)\nInterning at BNP Paribas, building Noema.", TODAY)
    check("weave", placed is not None and bool(placed[1].strip()),
          f"placed={placed}")


def eval_past_tense():
    out = memory_judge.rewrite_past(["In Paris for the internship."])
    check("past", out is not None and "was" in out[0].lower(), f"out={out}")


def eval_expand():
    words = [w.lower() for w in memory_judge.expand_query(
        "when was that turkish trip again?")]
    check("expand", any(w in words for w in ("istanbul", "turkey", "turquie")),
          f"keywords={words}")


def eval_journal_line():
    lines = memory_judge.summarize_chats([{
        "title": "Basel questions",
        "messages": [
            {"role": "user", "content": "what is the output floor percentage?"},
            {"role": "assistant", "content": "72.5% under Basel III final."},
        ],
    }])
    check("journal", lines is not None and len(lines) == 1 and len(lines[0]) < 200,
          f"lines={lines}")


if __name__ == "__main__":
    print("live memory-judge eval (real LLM calls)…")
    for step in (eval_until_and_style, eval_retire, eval_note_reversal,
                 eval_weave, eval_past_tense, eval_expand, eval_journal_line):
        try:
            step()
        except Exception as exc:  # noqa: BLE001
            check(step.__name__, False, f"unexpected {type(exc).__name__}: {exc}")
    passed = sum(1 for _n, ok, _d in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} scenarios passed")
    sys.exit(0 if passed == len(RESULTS) else 1)
