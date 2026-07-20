"""Judge + report statistics tests — no network, no LLM:

    backend/.venv/bin/python tests/test_judge_report.py

Covers: the v2 judge rubric (false-premise/unanswerable symmetry, numeric equivalence),
opt-in throttling, bootstrap CIs, the exact McNemar flip test, paired delta CI, run-cost
pricing, and the provenance stamps (judge rubric version + graph search recipe) landing
in an assembled report.
"""

import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.bench import report, scoring  # noqa: E402


def test_judge_rubric_v2():
    s = scoring._JUDGE_SYS
    assert scoring.JUDGE_PROMPT_VERSION == "v2"
    assert "false premise" in s and "unanswerable" in s, "false-premise symmetry rule missing"
    assert "CORRECT" in s, "refusal-on-invalid-gold rule missing"
    assert "rounding" in s and "currency" in s, "numeric equivalence rule missing"
    assert "unavailable when a gold answer exists is wrong" in s, "abstention penalty lost"
    print("  rubric_v2: numeric + false-premise rules present, version stamped ✓")


def test_throttle_is_opt_in():
    import os
    os.environ.pop("JUDGE_RPM", None)
    t0 = time.perf_counter()
    for _ in range(50):
        scoring._throttle()
    assert time.perf_counter() - t0 < 0.05, "unset JUDGE_RPM must mean full speed"
    print("  throttle: opt-in only — no pacing unless JUDGE_RPM is set ✓")


def test_bootstrap_ci():
    assert report._bootstrap_ci([1.0] * 3) is None, "too few points must read None"
    all_true = report._bootstrap_ci([1.0] * 50)
    assert all_true == [1.0, 1.0]
    mixed = report._bootstrap_ci([1.0] * 35 + [0.0] * 15)  # 70% over n=50
    lo, hi = mixed
    assert lo < 0.7 < hi and 0.5 < lo and hi < 0.9, f"implausible CI {mixed}"
    assert report._bootstrap_ci([1.0] * 35 + [0.0] * 15) == mixed, "must be deterministic (seeded)"
    print(f"  bootstrap: 70%/n=50 -> CI [{lo}, {hi}], deterministic ✓")


def test_mcnemar():
    assert report._mcnemar_p(0, 0) is None
    assert report._mcnemar_p(5, 5) == 1.0, "perfectly balanced flips = pure chance"
    p_strong = report._mcnemar_p(12, 1)
    assert p_strong < 0.01, f"12-vs-1 flips must be significant, got {p_strong}"
    p_weak = report._mcnemar_p(3, 1)
    assert p_weak > 0.05, f"3-vs-1 flips must NOT be significant, got {p_weak}"
    print(f"  mcnemar: 12/1 -> p={p_strong}, 3/1 -> p={p_weak}, 5/5 -> p=1.0 ✓")


def _rec(config, qid, correct, error=None):
    r = {"config": config, "qid": qid, "type": "factoid", "ok": error is None,
         "answer": "x", "em": False, "f1": 0.5,
         "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "cached_tokens": 200},
         "judge_usage": {"prompt_tokens": 400, "completion_tokens": 50},
         "judge": {"correct": correct, "score": 1.0 if correct else 0.0,
                   "note": "", "judge_model": "gpt-5.4-mini"}}
    if error:
        r.update({"error": error, "judge": None, "usage": None})
    return r


def test_assemble_stats_cost_provenance():
    gold = [{"id": f"q{i}", "question": f"Q{i}?", "answer": "A", "type": "factoid"}
            for i in range(30)]
    records = []
    for i in range(30):
        rag_ok = i < 18                      # rag: 18/30
        hy_ok = rag_ok or i in (18, 19, 20)  # hybrid gains 3, loses 0
        records.append(_rec("rag", f"q{i}", rag_ok))
        records.append(_rec("hybrid", f"q{i}", hy_ok))
    prepared = {"gold_source": "human", "tokens": 100_000, "docs": 10,
                "cap_tokens": 100_000, "corpus_hash": "abc123"}
    rep = report.assemble(
        run_id="t", dataset="d", prepared=prepared,
        build={"models": {"extract": "gpt-5.4-mini", "embed": "text-embedding-3-large"}},
        configs=["rag", "hybrid"], gold=gold, records=records,
        answer_model="gpt-5.4-mini", scope="auto",
        graph_search_recipe="rrf", judge_prompt_version="v2")

    rows = {r["config"]: r for r in rep["headline"]}
    assert rows["rag"]["judge_accuracy"] == 0.6
    ci = rows["rag"]["judge_accuracy_ci95"]
    assert ci and ci[0] < 0.6 < ci[1], f"CI must bracket the point estimate: {ci}"

    fusion = rep["fusion"]
    assert fusion["hybrid_gained_over_rag"] == 3 and fusion["hybrid_lost_vs_rag"] == 0
    assert fusion["mcnemar_p"] == 0.25, f"3-0 flips -> exact p 0.25, got {fusion['mcnemar_p']}"
    assert fusion["hybrid_delta_ci95"], "paired delta CI missing"

    cost = rep["run_cost_usd"]
    assert cost["generation_usd"] and cost["judging_usd"] and cost["total_usd"], cost
    assert abs(cost["total_usd"] - (cost["generation_usd"] + cost["judging_usd"])) < 1e-6

    prov = rep["provenance"]
    assert prov["judge_prompt_version"] == "v2" and prov["graph_search_recipe"] == "rrf"
    assert rep["schema"] == 4

    md = report.render_markdown(rep)
    assert "95% CI" in md and "McNemar" in md and "run total" in md
    print("  assemble: CIs, McNemar, priced cost, provenance stamps, markdown render ✓")


def test_evidence_source_and_lightrag_fusion():
    windows = ["alpha beta gamma delta", "the model uses BERT embeddings for retrieval",
               "unrelated tail text here"]
    assert scoring.evidence_windows(windows, "uses BERT embeddings for retrieval") == {2}
    assert scoring.evidence_windows(windows, "totally absent phrase qqq") == set()

    gold = [{"id": f"q{i}", "question": f"Q{i}?", "answer": "A", "type": "factoid"}
            for i in range(6)]
    records = []
    for i in range(6):
        records.append(_rec("rag", f"q{i}", i < 3))                       # rag: 3/6
        hy = _rec("lightrag_hybrid", f"q{i}", i < 4)                      # gains 1, loses 0
        hy["evidence_source_hit"] = i % 2 == 0                            # 3/6 sourced right
        hy["retrieved"] = [{"origin": "vector"}, {"origin": "lightrag"}]
        records.append(hy)
    prepared = {"gold_source": "human", "tokens": 10_000, "docs": 2,
                "cap_tokens": 10_000, "corpus_hash": "abc123"}
    rep = report.assemble(
        run_id="t2", dataset="d", prepared=prepared,
        build={"models": {"extract": "gpt-5.4-mini", "embed": "text-embedding-3-large"}},
        configs=["rag", "lightrag_hybrid"], gold=gold, records=records,
        answer_model="gpt-5.4-mini", scope="auto")

    rows = {r["config"]: r for r in rep["headline"]}
    assert rows["lightrag_hybrid"]["evidence_source_recall"] == 0.5
    assert rows["rag"]["evidence_source_recall"] is None, "no fact store -> no source metric"
    lf = rep["fusion_lightrag"]
    assert lf["paired_questions"] == 6 and lf["hybrid_gained_over_rag"] == 1
    assert lf["graph_share_of_context"] == 0.5, "supplement share must count non-vector origins"
    assert rep["fusion"] is None, "no hybrid config ran -> no graph fusion block"

    md = report.render_markdown(rep)
    assert "lightrag_hybrid vs rag" in md and "evidence source" in md
    print("  evidence source recall + lightrag fusion block aggregate and render ✓")


def test_unpriced_judge_reads_none():
    cost = report._run_cost(
        {"generation": {"prompt_tokens": 1000, "completion_tokens": 10},
         "judging": {"prompt_tokens": 500, "completion_tokens": 5}},
        "gpt-5.4-mini", ["gemini-2.5-flash"])
    assert cost["generation_usd"] is not None
    assert cost["judging_usd"] is None, "an unpriced judge must read None, never a made-up number"
    assert cost["total_usd"] == cost["generation_usd"]
    print("  cost: unknown judge model -> None, not a fabricated price ✓")


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    print("running judge+report tests…")
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
