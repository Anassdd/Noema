"""Report assembly — schema v1. One report per run; the schema is FROZEN so any two
reports (Mac vs company, July vs later, method A vs method B) merge into one table.

Blocks: provenance -> headline (one row per config, lift over closed_book) ->
slices by question type -> fusion diagnostics (hybrid) -> failure gallery -> raw
per-question records (so new metrics can be recomputed later without re-running).
"""

from __future__ import annotations

import time

SCHEMA_VERSION = 1


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def _rate(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def _row(config: str, recs: list[dict]) -> dict:
    gen_prompt = sum((r.get("usage") or {}).get("prompt_tokens", 0) or 0 for r in recs)
    gen_out = sum((r.get("usage") or {}).get("completion_tokens", 0) or 0 for r in recs)
    return {
        "config": config,
        "n": len(recs),
        "judged": sum(1 for r in recs if r["judge"].get("correct") is not None),
        "judge_accuracy": _rate([r["judge"].get("correct") for r in recs]),
        "judge_score": _mean([r["judge"].get("score") for r in recs]),
        "em": _rate([r.get("em") for r in recs]),
        "f1": _mean([r.get("f1") for r in recs]),
        "evidence_recall": _rate([r.get("evidence_hit") for r in recs
                                  if "evidence_hit" in r]) if any("evidence_hit" in r for r in recs) else None,
        "latency_ms_avg": round(_mean([r.get("latency_ms") for r in recs]) or 0),
        "tokens_per_q": round((gen_prompt + gen_out) / len(recs)) if recs else 0,
        "errors": sum(1 for r in recs if r.get("error")),
    }


def _fusion(recs: list[dict]) -> dict | None:
    """For the hybrid config: how much did the graph actually contribute, and did it help?"""
    if not recs:
        return None
    shares = []
    with_graph, without_graph = [], []
    for r in recs:
        retrieved = r.get("retrieved", [])
        if not retrieved:
            continue
        g = sum(1 for c in retrieved if c["origin"] == "graph")
        shares.append(g / len(retrieved))
        (with_graph if g else without_graph).append(r["judge"].get("correct"))
    return {
        "graph_share_of_context": _mean(shares),
        "accuracy_when_graph_present": _rate(with_graph),
        "accuracy_when_graph_absent": _rate(without_graph),
        "questions_with_graph_context": len(with_graph),
    }


def assemble(*, run_id: str, dataset: str, prepared: dict, build: dict,
             configs: list[str], gold: list[dict], records: list[dict],
             answer_model: str) -> dict:
    by_config = {c: [r for r in records if r["config"] == c] for c in configs}
    headline = [_row(c, by_config[c]) for c in configs]

    floor = next((row["judge_accuracy"] for row in headline if row["config"] == "closed_book"), None)
    for row in headline:
        row["lift_over_closed_book"] = (
            round(row["judge_accuracy"] - floor, 4)
            if floor is not None and row["judge_accuracy"] is not None
            and row["config"] != "closed_book" else None)

    slices = {}
    for qtype in sorted({q.get("type", "factoid") for q in gold}):
        slices[qtype] = [
            {"config": c,
             "judge_accuracy": _rate([r["judge"].get("correct") for r in by_config[c]
                                      if r.get("type") == qtype]),
             "f1": _mean([r.get("f1") for r in by_config[c] if r.get("type") == qtype])}
            for c in configs
        ]

    # Gallery: the 5 worst failures PER CONFIG (not 10 overall — at 1000 questions one
    # weak config would monopolize it). Every failure stays queryable in the run JSON.
    by_q = {q["id"]: q for q in gold}
    gallery = []
    for c in configs:
        worst = sorted(
            (r for r in by_config[c] if r["judge"].get("correct") is False),
            key=lambda r: (r["judge"].get("score") or 0))[:5]
        gallery += [{
            "config": r["config"], "qid": r["qid"],
            "question": by_q.get(r["qid"], {}).get("question", ""),
            "gold": by_q.get(r["qid"], {}).get("answer", ""),
            "answer": (r.get("answer") or "")[:400],
            "note": r["judge"].get("note", ""), "error": r.get("error"),
        } for r in worst]

    usage_totals = {"generation": {}, "judging": {}}
    for r in records:
        for k in ("prompt_tokens", "completion_tokens", "cached_tokens"):
            usage_totals["generation"][k] = usage_totals["generation"].get(k, 0) + ((r.get("usage") or {}).get(k) or 0)
            usage_totals["judging"][k] = usage_totals["judging"].get(k, 0) + ((r.get("judge_usage") or {}).get(k) or 0)

    return {
        "schema": SCHEMA_VERSION,
        "run_id": run_id,
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "dataset": dataset,
        "prepared": prepared,
        "build": {k: build.get(k) for k in ("fingerprint", "save_name", "cap_tokens",
                                            "models", "built_at", "build_seconds",
                                            "nodes", "edges", "chunks", "tokens")},
        "answer_model": answer_model,
        "gold_source": prepared.get("gold_source",
                                    "generated by the bench (evidence-gated + judge-verified)"),
        "examples": [next(({"type": t, "question": q["question"], "answer": q["answer"]}
                           for q in gold if q.get("type") == t), None)
                     for t in ("factoid", "synthesis", "global", "null")],
        "graph_health": build.get("graph_health"),
        "usage_totals": usage_totals,
        "headline": headline,
        "verdict": _verdict(headline, _fusion(by_config.get("hybrid", []))),
        "slices": slices,
        "fusion": _fusion(by_config.get("hybrid", [])),
        "failure_gallery": gallery,
        "records": records,
    }


def _verdict(headline: list[dict], fusion: dict | None) -> str:
    """The three sentences a reader gets before any table."""
    total_n = sum(r["n"] for r in headline)
    total_judged = sum(r.get("judged", 0) for r in headline)
    coverage = total_judged / total_n if total_n else 0
    scored = [r for r in headline if r["judge_accuracy"] is not None]
    if not scored:
        return "No scored answers — check the run log."
    if coverage < 0.7:
        return (f"⚠ only {coverage:.0%} of answers were judged (judge rate-limited?) — "
                "accuracy figures are UNRELIABLE; re-judge this run before reading them.")
    best = max(scored, key=lambda r: r["judge_accuracy"])
    parts = [f"Best config: {best['config']} at {best['judge_accuracy']:.0%}"]
    if best.get("lift_over_closed_book") is not None:
        parts[-1] += f" ({best['lift_over_closed_book']:+.0%} over closed-book)"
    floor = next((r for r in scored if r["config"] == "closed_book"), None)
    if floor is not None:
        parts.append(f"closed-book floor {floor['judge_accuracy']:.0%} — "
                     f"{'clean corpus, lifts are real' if floor['judge_accuracy'] <= 0.2 else 'the model partly knows this corpus; read lifts, not raw scores'}")
    if fusion and fusion.get("graph_share_of_context") is not None:
        parts.append(f"the graph supplied {fusion['graph_share_of_context']:.0%} of the hybrid's context")
    return ". ".join(parts) + "."


# ---- markdown render: a finished deliverable ------------------------------------
# The document is complete on the results side; the narrative spots a human should
# write are marked `> ✎ TO COMPLETE`. Hand the file to a reader as-is or finish
# those blocks first.

_CONFIG_EXPLAIN = {
    "closed_book": "the generator alone, NO retrieval — the contamination floor: what the model already knew",
    "rag": "contextual vector base only (hybrid dense + BM25 over LLM-situated chunks)",
    "graph": "temporal knowledge graph only (entities + facts, Graphiti)",
    "hybrid": "both stores, rankings fused (RRF) — the product configuration",
}


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.0f}%"


def render_markdown(report: dict) -> str:
    b = report["build"]
    p = report["prepared"]
    lines = [
        f"# Memory-method benchmark report — `{report['dataset']}`",
        "",
        f"*Run `{report['run_id']}` · {report['at']} · schema v{report['schema']}*",
        "",
        "## 1. Summary",
        "",
        f"> **{report['verdict']}**",
        "",
        "> ✎ TO COMPLETE — two or three sentences of interpretation: what this run was "
        "meant to establish, and what you conclude from it.",
        "",
        "## 2. Benchmark & corpus",
        "",
        f"- **Dataset**: `{report['dataset']}` — corpus of {p['tokens']:,} tokens across "
        f"{p['docs']} documents (token cap {p['cap_tokens']:,}), corpus hash `{p['corpus_hash']}`",
        f"- **Gold questions**: {sum(r['n'] for r in report['headline'][:1])} used, "
        f"source: **{report['gold_source']}**",
        "",
        "> ✎ TO COMPLETE — describe the benchmark in your own words: where the documents "
        "come from, why this dataset was chosen, what it represents.",
        "",
        "### Example questions",
        "",
    ]
    for ex in report.get("examples", []):
        if ex:
            lines.append(f"- *({ex['type']})* **{ex['question']}** → {ex['answer']}")
    lines += [
        "",
        "## 3. Setup",
        "",
        f"- **Answer model** (identical for every config): `{report['answer_model']}`",
        f"- **Extraction model** (graph build): `{b['models']['extract']}` · "
        f"**embeddings**: `{b['models'].get('embed', '?')}`",
        f"- **Memory build** `{b['fingerprint']}` → checkpointed as save **{b['save_name']}**: "
        f"{b.get('nodes', '?')} entities · {b.get('edges', '?')} facts · {b.get('chunks', '?')} chunks"
        + (f" · built in {b['build_seconds']}s" if b.get("build_seconds") else ""),
        "",
        "Configurations compared (same memory, same questions — only retrieval differs):",
        "",
    ]
    for r in report["headline"]:
        lines.append(f"- **{r['config']}** — {_CONFIG_EXPLAIN.get(r['config'], '')}")

    lines += [
        "",
        "## 4. Results",
        "",
        "| config | n | judge acc | lift vs closed-book | EM | F1 | evidence recall | latency avg | tok/q | errors |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["headline"]:
        lines.append(
            f"| {r['config']} | {r['n']} | {_pct(r['judge_accuracy'])} | "
            f"{_pct(r['lift_over_closed_book']) if r['lift_over_closed_book'] is not None else '—'} | "
            f"{_pct(r['em'])} | {r['f1'] if r['f1'] is not None else '—'} | "
            f"{_pct(r['evidence_recall'])} | {r['latency_ms_avg']} ms | {r['tokens_per_q']} | {r['errors']} |")

    lines += [
        "",
        "*How to read this: **judge acc** = answers graded correct against the gold answer; "
        "**lift** = points above the closed-book floor (what retrieval actually earned); "
        "**evidence recall** = how often the gold evidence was among the retrieved passages "
        "(separates retrieval failures from generation failures).*",
        "",
        "### By question type",
        "",
    ]
    for qtype, rows in report["slices"].items():
        label = "abstention (correct = refusing)" if qtype == "null" else qtype
        lines.append(f"**{label}** — " + " · ".join(
            f"{r['config']}: {_pct(r['judge_accuracy'])}" for r in rows))

    fusion = report.get("fusion")
    if fusion:
        lines += ["", "### Fusion diagnostics (hybrid)", "",
                  f"- graph share of retrieved context: {_pct(fusion['graph_share_of_context'])}",
                  f"- accuracy when the graph contributed: {_pct(fusion['accuracy_when_graph_present'])} "
                  f"(vs {_pct(fusion['accuracy_when_graph_absent'])} without, "
                  f"{fusion['questions_with_graph_context']} questions)"]

    health = report.get("graph_health")
    if health:
        lines += ["", "### Graph health", "",
                  f"- orphan entities: {health['orphans']} · archived facts: {health['archived_facts']} · "
                  f"duplicate-name suspects: {health['duplicate_name_suspects']} · episodes: {health['episodes']}"]

    u = report.get("usage_totals", {})
    if u:
        g, j = u.get("generation", {}), u.get("judging", {})
        lines += ["", "### Cost (tokens; build cost tracked on the provider dashboard)", "",
                  f"- generation: {g.get('prompt_tokens', 0):,} in / {g.get('completion_tokens', 0):,} out "
                  f"({g.get('cached_tokens', 0):,} cached)",
                  f"- judging: {j.get('prompt_tokens', 0):,} in / {j.get('completion_tokens', 0):,} out"]

    if report["failure_gallery"]:
        lines += ["", "## 5. Failure analysis", "",
                  "*The 5 lowest-scored failures per configuration (every record is in the run JSON):*", ""]
        for f in report["failure_gallery"]:
            lines += [f"- **{f['qid']} / {f['config']}** — {f['question']}",
                      f"  - gold: {f['gold']}",
                      f"  - got: {f['answer'] or '(error: ' + str(f.get('error')) + ')'}",
                      f"  - judge: {f['note']}"]
        lines += ["", "> ✎ TO COMPLETE — patterns you see in the failures (retrieval misses? "
                      "reasoning errors? bad questions?).", ""]

    lines += [
        "## 6. Scope & limitations",
        "",
        f"- Corpus capped at {p['cap_tokens']:,} tokens — results are comparative "
        "(method vs method on identical conditions), not absolute quality claims.",
        f"- {sum(r['n'] for r in report['headline'][:1])} questions: differences of a few "
        "points are within noise at this sample size.",
        "",
        "> ✎ TO COMPLETE — anything specific to this run worth flagging.",
        "",
        "---",
        f"*Reproduction: dataset `{report['dataset']}` @ corpus hash `{p['corpus_hash']}`, "
        f"build fingerprint `{b['fingerprint']}`, configs {[r['config'] for r in report['headline']]}, "
        f"run `{report['run_id']}`. Raw per-question records: `runs/{report['run_id']}.json`.*",
        "",
    ]
    return "\n".join(lines)
