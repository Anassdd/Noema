"""Report assembly — schema v1. One report per run; the schema is FROZEN so any two
reports (Mac vs company, July vs later, method A vs method B) merge into one table.

Blocks: provenance -> headline (one row per config, lift over closed_book) ->
slices by question type -> fusion diagnostics (hybrid) -> failure gallery -> raw
per-question records (so new metrics can be recomputed later without re-running).
"""

from __future__ import annotations

import time

# v2: quality metrics exclude infrastructure-error records; per-config judge coverage;
# honest paired fusion diagnostic; judge/scope/anchoring provenance recorded.
SCHEMA_VERSION = 2


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


def _rate(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def _judge(rec: dict) -> dict:
    """A record's verdict, tolerating error records that never carried one."""
    return rec.get("judge") or {}


def _row(config: str, recs: list[dict]) -> dict:
    # Infrastructure failures (burned generations) are NOT answers — every quality metric
    # is computed over `answered` only, so a provider outage can never masquerade as low
    # accuracy. `n` still shows the full question count; `answered`/`errors` expose the gap.
    answered = [r for r in recs if not r.get("error")]
    errored = [r for r in recs if r.get("error")]
    correct = [_judge(r).get("correct") for r in answered]
    judged = [c for c in correct if c is not None]
    gen_prompt = sum((r.get("usage") or {}).get("prompt_tokens", 0) or 0 for r in answered)
    gen_out = sum((r.get("usage") or {}).get("completion_tokens", 0) or 0 for r in answered)
    return {
        "config": config,
        "n": len(recs),
        "answered": len(answered),
        "errors": len(errored),
        "judged": len(judged),
        # Fraction of ANSWERS that got a verdict — the honesty gate: accuracy is only
        # trustworthy when this is high (a half-dead judge otherwise hides behind a number).
        "coverage": round(len(judged) / len(answered), 4) if answered else None,
        "judge_accuracy": _rate(correct),
        "judge_score": _mean([_judge(r).get("score") for r in answered]),
        "em": _rate([r.get("em") for r in answered]),
        "f1": _mean([r.get("f1") for r in answered]),
        "evidence_recall": _rate([r.get("evidence_hit") for r in answered
                                  if "evidence_hit" in r]) if any("evidence_hit" in r for r in answered) else None,
        "evidence_overlap": _mean([r.get("evidence_overlap") for r in answered
                                   if r.get("evidence_overlap") is not None])
                            if any(r.get("evidence_overlap") is not None for r in answered) else None,
        "latency_ms_avg": round(_mean([r.get("latency_ms") for r in answered]) or 0),
        "tokens_per_q": round((gen_prompt + gen_out) / len(answered)) if answered else 0,
    }


def _fusion(by_config: dict[str, list[dict]]) -> dict | None:
    """Did fusing the graph into the vector base actually help, measured HONESTLY?

    The old diagnostic ('accuracy when the graph contributed') was tautological: hybrid
    interleaves the two rankings, so the graph is present in almost every question and the
    'absent' bucket is empty. The real question is paired: on the questions BOTH rag and
    hybrid answered, how often did adding the graph FLIP a rag-correct answer to wrong (it
    displaced evidence) versus rescue a rag-wrong one? That is the number that says whether
    the product's fusion earns its place."""
    hy = [r for r in by_config.get("hybrid", []) if not r.get("error")]
    if not hy:
        return None
    shares = []
    for r in hy:
        retrieved = r.get("retrieved", [])
        if retrieved:
            shares.append(sum(1 for c in retrieved if c["origin"] == "graph") / len(retrieved))
    out = {
        "graph_share_of_context": _mean(shares),
        "note": ("share of final context items that came from the graph — judge fusion by "
                 "the paired win/loss below, not by this share."),
    }
    rag = {r["qid"]: r for r in by_config.get("rag", []) if not r.get("error")}
    hyq = {r["qid"]: r for r in hy}
    both = rag.keys() & hyq.keys()
    if both:
        gained = sum(1 for q in both if _judge(hyq[q]).get("correct") and not _judge(rag[q]).get("correct"))
        lost = sum(1 for q in both if _judge(rag[q]).get("correct") and not _judge(hyq[q]).get("correct"))
        out.update({"paired_questions": len(both),
                    "hybrid_gained_over_rag": gained, "hybrid_lost_vs_rag": lost})
    return out


def assemble(*, run_id: str, dataset: str, prepared: dict, build: dict,
             configs: list[str], gold: list[dict], records: list[dict],
             answer_model: str, scope: str = "auto") -> dict:
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
             "judge_accuracy": _rate([_judge(r).get("correct") for r in by_config[c]
                                      if r.get("type") == qtype and not r.get("error")]),
             "f1": _mean([r.get("f1") for r in by_config[c]
                          if r.get("type") == qtype and not r.get("error")])}
            for c in configs
        ]

    # Gallery: the 5 worst failures PER CONFIG (not 10 overall — at 1000 questions one
    # weak config would monopolize it). Only genuine wrong answers, never error records
    # (those are surfaced separately as infrastructure failures, not answer quality).
    by_q = {q["id"]: q for q in gold}
    gallery = []
    for c in configs:
        worst = sorted(
            (r for r in by_config[c] if not r.get("error") and _judge(r).get("correct") is False),
            key=lambda r: (_judge(r).get("score") or 0))[:5]
        gallery += [{
            "config": r["config"], "qid": r["qid"],
            "question": by_q.get(r["qid"], {}).get("question", ""),
            "gold": by_q.get(r["qid"], {}).get("answer", ""),
            "answer": (r.get("answer") or "")[:400],
            "note": _judge(r).get("note", ""), "error": r.get("error"),
        } for r in worst]

    usage_totals = {"generation": {}, "judging": {}}
    for r in records:
        for k in ("prompt_tokens", "completion_tokens", "cached_tokens"):
            usage_totals["generation"][k] = usage_totals["generation"].get(k, 0) + ((r.get("usage") or {}).get(k) or 0)
            usage_totals["judging"][k] = usage_totals["judging"].get(k, 0) + ((r.get("judge_usage") or {}).get(k) or 0)

    # Provenance a stakeholder needs to trust (or discount) the numbers: who judged, whether
    # any verdict fell back to the generator's own model (self-preference), which retrieval
    # scope ran, and whether questions were document-anchored (which lifts the closed-book floor).
    judge_models = sorted({_judge(r).get("judge_model") for r in records
                           if _judge(r).get("judge_model")})
    provenance = {
        "judge_models": judge_models,
        "judge_used_fallback": any("(fallback)" in (m or "") for m in judge_models),
        "scope": scope,
        "questions_document_anchored": any(r.get("asked") for r in records),
        "answer_model_resolved": sorted({r.get("answer_model") for r in records
                                         if r.get("answer_model")}),
    }

    fusion = _fusion(by_config)
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
        "provenance": provenance,
        "gold_source": prepared.get("gold_source",
                                    "generated by the bench (evidence-gated + judge-verified)"),
        "examples": [next(({"type": t, "question": q["question"], "answer": q["answer"]}
                           for q in gold if q.get("type") == t), None)
                     for t in ("factoid", "synthesis", "global", "null")],
        "graph_health": build.get("graph_health"),
        "usage_totals": usage_totals,
        "headline": headline,
        "verdict": _verdict(headline, fusion, provenance),
        "slices": slices,
        "fusion": fusion,
        "failure_gallery": gallery,
        "records": records,
    }


def _verdict(headline: list[dict], fusion: dict | None, provenance: dict | None = None) -> str:
    """The sentences a reader gets before any table — warnings FIRST, so an outage or a
    half-dead judge can never hide behind a confident-looking accuracy number."""
    warnings = []
    incomplete = [r for r in headline if r.get("answered") is not None and r["answered"] < r["n"]]
    if incomplete:
        warnings.append(
            "⚠ incomplete: " + ", ".join(
                f"{r['config']} answered {r['answered']}/{r['n']} ({r['errors']} infra errors)"
                for r in incomplete)
            + " — the missing questions are excluded from accuracy (not scored wrong); "
              "resume the run to fill them before comparing configs")
    thin = [r for r in headline if r.get("coverage") is not None
            and r["coverage"] < 0.7 and r.get("answered")]
    if thin:
        warnings.append(
            "⚠ low judge coverage: " + ", ".join(
                f"{r['config']} {r['coverage']:.0%}" for r in thin)
            + " — those accuracies are unreliable; re-judge before trusting")
    if provenance and provenance.get("judge_used_fallback"):
        warnings.append("⚠ some verdicts fell back to the generator's own model "
                        "(self-preference risk) — see provenance.judge_models")

    scored = [r for r in headline if r["judge_accuracy"] is not None
              and r.get("answered") == r["n"]]  # only fully-answered configs are comparable
    if not scored:
        tail = ("No config is complete enough to rank — finish/resume the run, then re-read."
                if warnings else "No scored answers — check the run log.")
        return " ".join(warnings + [tail])

    best = max(scored, key=lambda r: r["judge_accuracy"])
    parts = [f"Best complete config: {best['config']} at {best['judge_accuracy']:.0%}"]
    if best.get("lift_over_closed_book") is not None:
        parts[-1] += f" ({best['lift_over_closed_book']:+.0%} over closed-book)"
    floor = next((r for r in scored if r["config"] == "closed_book"), None)
    if floor is not None:
        parts.append(f"closed-book floor {floor['judge_accuracy']:.0%} — "
                     f"{'clean corpus, lifts are real' if floor['judge_accuracy'] <= 0.2 else 'the model partly knows this corpus; read lifts, not raw scores'}")
    if fusion and fusion.get("hybrid_lost_vs_rag") is not None:
        parts.append(f"fusion vs rag (paired): fixed {fusion['hybrid_gained_over_rag']}, "
                     f"broke {fusion['hybrid_lost_vs_rag']} of {fusion['paired_questions']}")
    return " ".join(warnings + [". ".join(parts) + "."])


# ---- markdown render: a finished deliverable ------------------------------------
# The document is complete on the results side; the narrative spots a human should
# write are marked `> ✎ TO COMPLETE`. Hand the file to a reader as-is or finish
# those blocks first.

_CONFIG_EXPLAIN = {
    "closed_book": "the generator alone, NO retrieval — the contamination floor: what the model already knew",
    "rag": "contextual vector base only (hybrid dense + BM25 over LLM-situated chunks)",
    "graph": "temporal knowledge graph only (entities + facts, Graphiti)",
    "hybrid": "both stores — the full contextual top-k plus novelty-gated graph facts "
              "appended (supplement fusion; the product configuration)",
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
        (lambda pv: f"- **Judge**: {', '.join(f'`{m}`' for m in pv['judge_models']) or 'unrecorded'}"
                    f"{' ⚠ includes a self-judged fallback' if pv.get('judge_used_fallback') else ''} · "
                    f"**scope**: `{pv.get('scope', '?')}` · "
                    f"**questions {'document-anchored' if pv.get('questions_document_anchored') else 'used as-is'}**"
         )(report.get("provenance", {})),
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
        "| config | answered | judged | judge acc | lift vs closed-book | EM | F1 | evidence recall | evidence overlap | latency avg | tok/q |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["headline"]:
        answered = f"{r.get('answered', r['n'])}/{r['n']}"
        if r.get("errors"):
            answered += f" ⚠{r['errors']} err"
        lines.append(
            f"| {r['config']} | {answered} | {r.get('judged', '—')} | {_pct(r['judge_accuracy'])} | "
            f"{_pct(r['lift_over_closed_book']) if r['lift_over_closed_book'] is not None else '—'} | "
            f"{_pct(r['em'])} | {r['f1'] if r['f1'] is not None else '—'} | "
            f"{_pct(r['evidence_recall'])} | {_pct(r['evidence_overlap'])} | "
            f"{r['latency_ms_avg']} ms | {r['tokens_per_q']} |")

    lines += [
        "",
        "*How to read this: **answered** = questions that produced an answer (the rest hit "
        "infrastructure errors and are excluded from every accuracy figure, not scored wrong); "
        "**judged** = answers that received a verdict; **judge acc** = of those, the fraction "
        "graded correct against the gold answer; "
        "**lift** = points above the closed-book floor (what retrieval actually earned); "
        "**evidence recall** = how often the gold evidence *paragraph* was retrieved verbatim "
        "(a passage-retrieval metric — the graph reads 0 by construction, since it stores "
        "distilled facts, not verbatim text); **evidence overlap** = the wording-independent "
        "companion — how much of the evidence's content (entities, terms) the retrieval "
        "surfaced, which is the fair evidence signal for the graph.*",
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
        lines += ["", "### Fusion diagnostics (hybrid vs rag)", "",
                  f"- graph share of retrieved context: {_pct(fusion['graph_share_of_context'])} "
                  "*(judge fusion by the paired win/loss below, not by this share)*"]
        if fusion.get("paired_questions"):
            lines.append(
                f"- paired on {fusion['paired_questions']} questions both answered: fusion "
                f"**fixed {fusion['hybrid_gained_over_rag']}** rag-wrong answers and "
                f"**broke {fusion['hybrid_lost_vs_rag']}** rag-correct ones — "
                + ("fusion earns its place here" if fusion['hybrid_gained_over_rag'] > fusion['hybrid_lost_vs_rag']
                   else "fusion is net-negative on this corpus; the graph is displacing evidence chunks"))

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
