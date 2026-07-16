"""The bench runner — build once, query per config, score, report. Streamed as events.

The build's trick: the corpus is ingested DIRECTLY into a save of the default domain
(`__save__default__bench-<ds>-<cap>k-<fp>`), the exact shape the rest of the app
already understands — it appears in the graph page's Saves panel, the chat's memory
selector can answer from it, and restore/inspect/Dream all work on a copy without
ever touching the bench build. "Build once" is simply "that save exists".

A build fingerprint (corpus hash + cap + models + episode splitting) names the save;
any change mints a NEW save (versioned, keep-both) and old reports stay reproducible.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from typing import AsyncIterator

from app import pipeline, saves
from app.bench import scoring, store
from app.bench.datasets import split_windows
from app.bench.report import assemble, render_markdown
from app.config import settings
from app.graph.manager import graph_manager
from app.retrieval import ingest_markdown

EPISODE_TOKENS = 700
_EP_VERSION = "ep700-v1"

# config name -> (use_vector, use_graph); closed_book skips retrieval entirely.
CONFIGS = {
    "closed_book": (False, False),
    "rag": (True, False),
    "graph": (False, True),
    "hybrid": (True, True),
}

# After this many CONSECUTIVE questions fail with an infrastructure error (even after
# their own retries), the run pauses instead of burning budget scoring empty answers —
# the single defect that turned a provider outage into "hybrid lost". Everything answered
# so far is persisted; a re-run resumes from there. Override with BENCH_BREAKER.
_BREAKER = int(os.getenv("BENCH_BREAKER", "4"))
_ANSWER_TRIES = int(os.getenv("BENCH_ANSWER_TRIES", "4"))

# Substrings that mark an error as transient (worth a paced retry) rather than a bug.
_TRANSIENT = ("connection", "timeout", "timed out", "temporarily", "unavailable",
              "502", "503", "504", "429", "rate limit", "overloaded", "reset by peer",
              "econnreset", "read timed out", "service unavailable")


def _is_transient(exc: Exception) -> bool:
    return any(t in str(exc).lower() for t in _TRANSIENT)


async def _with_retry(make_awaitable, *, tries: int = _ANSWER_TRIES):
    """Await `make_awaitable()`, retrying transient failures with exponential backoff
    (5s, 10s, 20s, capped 45s) so a brief provider blip is ridden out rather than scored.
    A non-transient error, or the last try, re-raises."""
    for i in range(tries):
        try:
            return await make_awaitable()
        except Exception as exc:  # noqa: BLE001
            if i == tries - 1 or not _is_transient(exc):
                raise
            await asyncio.sleep(min(45.0, 5.0 * (2 ** i)))


def _fingerprint(corpus_hash: str, cap: int, extract_model: str) -> str:
    raw = f"{corpus_hash}|{cap}|{extract_model}|{settings.embed_model}|{_EP_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def _resolve_extract_model(explicit: str | None) -> str:
    """Bench default = the CHAT model (mini tier), per the bench spec: extraction is
    the dominant cost, current minis extract well, and the A2 spot-check vs the strong
    model is the quality gate. The product's own ingestion keeps the strong default."""
    return explicit or settings.chat_model


def _usage_add(total: dict, usage) -> None:
    if not usage:
        return
    u = usage if isinstance(usage, dict) else usage.__dict__
    for k in ("prompt_tokens", "completion_tokens", "cached_tokens"):
        total[k] = total.get(k, 0) + (u.get(k) or 0)


async def _build(dataset: str, docs: list[dict], domain: str, extract_model: str,
                 events: list, skip_episodes: set[str] | None = None,
                 skip_docs: set[str] | None = None) -> AsyncIterator[dict]:
    """Ingest the corpus into `domain` (RAG first — cheap, then the graph — slow),
    yielding progress. `skip_episodes` / `skip_docs` = graph episodes and RAG docs
    that survived an interrupted build; they are not re-ingested (resume)."""
    skip_episodes = skip_episodes or set()
    skip_docs = skip_docs or set()
    tokens = {"rag": {}, "graph_episodes": 0}

    for i, doc in enumerate(docs):
        if doc["id"] in skip_docs:
            yield {"phase": "rag_doc", "doc": doc["id"], "i": i + 1, "total": len(docs),
                   "chunks": 0, "skipped": True}
            continue
        info = await asyncio.to_thread(ingest_markdown, doc["text"], doc["id"], domain_id=domain)
        _usage_add(tokens["rag"], {"prompt_tokens": info.get("context_tokens", 0),
                                   "cached_tokens": info.get("cached_tokens", 0),
                                   "completion_tokens": 0})
        yield {"phase": "rag_doc", "doc": doc["id"], "i": i + 1, "total": len(docs),
               "chunks": info.get("chunks", 0)}

    from app.retrieval import VectorStore
    chunks_total = await asyncio.to_thread(lambda: VectorStore(domain).count())

    mem = await graph_manager.get(domain, extract_model)
    for i, doc in enumerate(docs):
        pieces = split_windows(doc["text"], EPISODE_TOKENS)
        for n, piece in enumerate(pieces):
            name = f"{doc['id']} · p{n + 1}"
            if name in skip_episodes:
                continue
            await mem.add_episode(piece, name=name)
            tokens["graph_episodes"] += 1
            yield {"phase": "graph_episode", "doc": doc["id"], "doc_i": i + 1,
                   "docs": len(docs), "episode": n + 1, "episodes": len(pieces)}

    snap = await mem.snapshot()
    events.append({"nodes": len(snap.nodes), "edges": len(snap.edges),
                   "chunks": chunks_total, "tokens": tokens,
                   "graph_health": await mem.graph_health()})


async def _answer(config: str, question: dict, domain: str, model: str | None,
                  doc_titles: dict[str, str] | None = None, scope: str = "auto") -> dict:
    """One question through one config; never raises — errors become a scored record.

    Questions from per-document gold (QASPER: "what dataset do THEY use?") presuppose
    their document — over a multi-doc corpus they are ambiguous, so retrieval,
    generation and judging all see a form anchored to the source document's title
    (stored as `asked`); the gold answers are untouched.

    Retrieval SCOPE follows the dataset, not the run: `scope="auto"` scopes each question to
    its own `doc_id` when the gold carries one (a per-document benchmark like QASPER — one
    paper in context, its intended condition) and searches the whole corpus when it doesn't
    (a corpus-wide dataset). `scope="corpus"` forces whole-corpus search — only to demonstrate
    the cross-document ambiguity that per-document questions suffer without scoping."""
    use_vector, use_graph = CONFIGS[config]
    q = question["question"]
    title = (doc_titles or {}).get(question.get("doc_id", ""))
    if title:
        q = f'Regarding the paper "{title}": {question["question"]}'
    scope_doc = None if scope == "corpus" else question.get("doc_id")
    rec = {"qid": question["id"], "config": config, "type": question.get("type", "factoid")}
    if title:
        rec["asked"] = q
    if scope_doc:
        rec["scoped_to"] = scope_doc
    t0 = time.perf_counter()

    async def _generate():
        chunks = []
        if use_vector or use_graph:
            chunks, _meta = await pipeline.retrieve(
                q, domain_id=domain, k=8, use_graph=use_graph, use_vector=use_vector,
                doc_id=scope_doc)
            res = await asyncio.to_thread(pipeline.grounded_answer, q, chunks, model=model)
        else:
            res = await asyncio.to_thread(pipeline.closed_book_answer, q, model=model)
        return chunks, res

    try:
        chunks, res = await _with_retry(_generate)
        rec["ok"] = True
        rec["answer"] = res.text or ""
        rec["usage"] = res.usage.__dict__ if res.usage else None
        rec["answer_model"] = getattr(res, "model", None)  # resolved snapshot, for provenance
        # evidence is checked against the FULL retrieved texts, then the archive keeps
        # only snippets — at 1000 questions full texts would make the run file huge.
        if (use_vector or use_graph) and question.get("evidence"):
            texts = [c.text for c in chunks]
            rec["evidence_hit"] = scoring.evidence_hit(question["evidence"], texts)
            rec["evidence_overlap"] = scoring.evidence_overlap(question["evidence"], texts)
        rec["retrieved"] = [
            {"origin": "graph" if c.chunk_id.startswith("graph:") else "vector",
             "doc_id": c.doc_id, "pages": c.pages, "text": (c.text or "")[:300]}
            for c in chunks
        ]
    except Exception as exc:  # noqa: BLE001 — an infra failure is NOT an answer
        # No answer was produced. Mark it and stop: it must not enter em/f1/judge or any
        # accuracy aggregate, or a provider outage would masquerade as a low score.
        rec.update({"ok": False, "answer": "", "error": str(exc)[:300], "usage": None,
                    "retrieved": [], "latency_ms": round((time.perf_counter() - t0) * 1000)})
        return rec

    rec["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    golds = [question["answer"]] + [a for a in question.get("alt_answers", []) if a]
    rec["em"] = any(scoring.exact_match(rec["answer"], g) for g in golds)
    rec["f1"] = round(max(scoring.token_f1(rec["answer"], g) for g in golds), 4)
    verdict = await asyncio.to_thread(scoring.judge, q, golds[0], rec["answer"],
                                      tuple(golds[1:]))
    rec["judge"] = {k: verdict.get(k) for k in ("correct", "score", "note", "judge_model")}
    _usage_add(rec.setdefault("judge_usage", {}), verdict.get("usage"))
    return rec


async def rejudge_run(dataset: str, run_id: str) -> AsyncIterator[dict]:
    """Re-score a stored run's answers with the CURRENT judge + gold (incl. alternative
    answers) — no generation re-paid; produces a new report from the same records."""
    old = store.load_run(dataset, run_id)
    if not old or not old.get("records"):
        yield {"phase": "error", "detail": "No stored records for that run."}
        return
    gold_map = {q["id"]: q for q in store.load_gold(dataset)}
    records = old["records"]
    yield {"phase": "start", "run_id": run_id, "rejudge": True, "records": len(records)}

    for i, rec in enumerate(records):
        q = gold_map.get(rec["qid"])
        if not q:
            continue
        if rec.get("error") or rec.get("ok") is False:
            # A burned generation has no answer to re-score — leave it flagged as an error,
            # never re-judge an empty string into a confident "wrong" (the old rejudge did).
            yield {"phase": "scored", "config": rec["config"], "i": i + 1,
                   "total": len(records), "qid": rec["qid"], "error": True}
            continue
        golds = [q["answer"]] + [a for a in q.get("alt_answers", []) if a]
        # Judge the SAME question the run answered: the document-anchored form when the run
        # used one, else the raw question — a rejudge must be a pure re-score, not a re-ask.
        judged_q = rec.get("asked") or q["question"]
        rec["em"] = any(scoring.exact_match(rec.get("answer", ""), g) for g in golds)
        rec["f1"] = round(max(scoring.token_f1(rec.get("answer", ""), g) for g in golds), 4)
        verdict = await asyncio.to_thread(
            scoring.judge, judged_q, golds[0], rec.get("answer", ""), tuple(golds[1:]))
        rec["judge"] = {k: verdict.get(k) for k in ("correct", "score", "note", "judge_model")}
        rec["judge_usage"] = {}
        _usage_add(rec["judge_usage"], verdict.get("usage"))
        yield {"phase": "scored", "config": rec["config"], "i": i + 1,
               "total": len(records), "qid": rec["qid"],
               "judge_correct": rec["judge"].get("correct"), "f1": rec["f1"]}

    new_id = store.new_run_id() + "-rejudged"
    report = assemble(run_id=new_id, dataset=dataset, prepared=old["prepared"],
                      build=old["build"], configs=[r["config"] for r in old["headline"]],
                      gold=list(gold_map.values()), records=records,
                      answer_model=old.get("answer_model", ""), scope=old.get("scope", "auto"))
    markdown = render_markdown(report)
    await asyncio.to_thread(store.save_run, dataset, new_id, report, markdown)
    yield {"phase": "report", "run_id": new_id, "report": {**report, "records": []}}
    yield {"phase": "done", "run_id": new_id}


async def run_bench(dataset: str, configs: list[str], *,
                    extract_model: str | None = None,
                    answer_model: str | None = None,
                    scope: str = "auto") -> AsyncIterator[dict]:
    """The whole cycle as an event stream: (build once) -> answer -> score -> report.

    `scope="auto"` follows the dataset: each question is scoped to its own source document
    when the gold carries a `doc_id` (per-document benchmarks like QASPER), else the whole
    corpus is searched. `scope="corpus"` forces whole-corpus search (to show the ambiguity)."""
    configs = [c for c in configs if c in CONFIGS] or list(CONFIGS)
    manifest = store.load_manifest(dataset)
    prepared = manifest.get("prepared")
    docs = store.load_corpus(dataset)
    gold = [q for q in store.load_gold(dataset) if q.get("status") == "approved"]

    if not prepared or not docs:
        yield {"phase": "error", "detail": "Dataset not prepared yet."}
        return
    if not gold:
        yield {"phase": "error", "detail": "No approved gold questions — approve some in the editor."}
        return

    extract = _resolve_extract_model(extract_model)
    fp = _fingerprint(prepared["corpus_hash"], prepared["cap_tokens"], extract)
    save_name = f"bench-{dataset}-{prepared['cap_tokens'] // 1000}k-{fp[:6]}"
    domain = saves.save_key("default", save_name)
    run_id = store.new_run_id()

    yield {"phase": "start", "run_id": run_id, "dataset": dataset, "configs": configs,
           "fingerprint": fp, "save_name": save_name, "questions": len(gold), "scope": scope}

    build = store.find_build(manifest, fp)
    existing = await asyncio.to_thread(saves.list_saves, "default", "graphiti")
    need_build = not (build and save_name in existing)
    skip_episodes: set[str] = set()
    skip_docs: set[str] = set()

    if not need_build:
        yield {"phase": "build_skip", "save_name": save_name, "built_at": build.get("built_at")}
    elif save_name in existing:
        # The save exists but the manifest doesn't know it: either a COMPLETE build
        # whose bookkeeping was lost (adopt it — never wipe paid work on suspicion),
        # or an interrupted one (RESUME: keep its episodes, re-ingest only the rest;
        # the vector side is cheap and rebuilds from scratch to avoid duplicates).
        expected = sum(len(split_windows(d["text"], EPISODE_TOKENS)) for d in docs)
        mem = await graph_manager.get(domain, extract)
        health = await mem.graph_health()
        if health.get("episodes") == expected:
            snap = await mem.snapshot()
            build = {"fingerprint": fp, "save_name": save_name, "domain": domain,
                     "cap_tokens": prepared["cap_tokens"], "corpus_hash": prepared["corpus_hash"],
                     "models": {"extract": extract, "embed": settings.embed_model},
                     "built_at": "unknown (adopted)", "adopted": True,
                     "nodes": len(snap.nodes), "edges": len(snap.edges),
                     "graph_health": health}
            manifest.setdefault("builds", []).append(build)
            store.save_manifest(dataset, manifest)
            need_build = False
            yield {"phase": "build_adopted", "save_name": save_name,
                   "detail": "existing complete build recognized — nothing rebuilt"}
        else:
            skip_episodes = await mem.all_episode_names()
            from app.retrieval import VectorStore
            skip_docs = await asyncio.to_thread(lambda: VectorStore(domain).doc_ids())
            yield {"phase": "build_resume", "save_name": save_name,
                   "detail": (f"interrupted build found — resuming: "
                              f"{len(skip_docs)}/{len(docs)} RAG docs and "
                              f"{len(skip_episodes)}/{expected} graph episodes already done")}

    if need_build:
        yield {"phase": "build_start", "save_name": save_name, "docs": len(docs),
               "extract_model": extract, "resumed_episodes": len(skip_episodes)}
        t0 = time.perf_counter()
        stats: list[dict] = []
        async with graph_manager.lock(domain):
            async for ev in _build(dataset, docs, domain, extract, stats,
                                   skip_episodes=skip_episodes, skip_docs=skip_docs):
                yield ev
        build = {
            "fingerprint": fp, "save_name": save_name, "domain": domain,
            "cap_tokens": prepared["cap_tokens"], "corpus_hash": prepared["corpus_hash"],
            "models": {"extract": extract, "embed": settings.embed_model},
            "built_at": time.strftime("%Y-%m-%d %H:%M"),
            "build_seconds": round(time.perf_counter() - t0),
            **(stats[0] if stats else {}),
        }
        manifest.setdefault("builds", []).append(build)
        store.save_manifest(dataset, manifest)
        yield {"phase": "build_done", **{k: build.get(k) for k in
               ("save_name", "nodes", "edges", "chunks", "build_seconds")}}

    doc_titles = {d["id"]: d["title"] for d in docs if d.get("title")}
    ans_model = answer_model or settings.chat_model

    # Resume key: stable across re-launches of the SAME run (build + configs + answer
    # model + scope + exact gold), so a crash/disconnect resumes instead of re-paying.
    # Editing gold or changing any of these mints a new key (a different experiment).
    gold_sig = hashlib.sha1(
        "\x00".join(f"{q['id']}={q.get('question', '')}={q.get('answer', '')}"
                    for q in gold).encode()).hexdigest()[:8]
    resume_key = hashlib.sha1(
        f"{fp}|{sorted(configs)}|{ans_model}|{scope}|{gold_sig}".encode()).hexdigest()[:16]

    # Load anything a prior attempt already answered. Dedup per (config, qid), preferring
    # a real answer over a stale error record; only OK answers count as "done" — an
    # errored question is retried on resume, never silently left scored-wrong.
    by_key: dict[tuple[str, str], dict] = {}
    for r in await asyncio.to_thread(store.load_records, dataset, resume_key):
        k = (r.get("config"), r.get("qid"))
        if k not in by_key or (not by_key[k].get("ok") and r.get("ok")):
            by_key[k] = r
    done = {k for k, r in by_key.items() if r.get("ok")}
    if done:
        yield {"phase": "query_resume", "answered": len(done),
               "detail": f"resuming — {len(done)} answers already saved, re-costing only the rest"}

    consecutive_errors = 0
    for config in configs:
        yield {"phase": "config_start", "config": config, "questions": len(gold)}
        for i, q in enumerate(gold):
            key = (config, q["id"])
            if key in done:
                yield {"phase": "scored", "config": config, "i": i + 1, "total": len(gold),
                       "qid": q["id"], "resumed": True}
                continue
            rec = await _answer(config, q, domain, answer_model, doc_titles, scope=scope)
            await asyncio.to_thread(store.append_record, dataset, resume_key, rec)
            by_key[key] = rec
            ev = {"phase": "scored", "config": config, "i": i + 1, "total": len(gold),
                  "qid": q["id"]}
            if rec.get("ok"):
                done.add(key)
                consecutive_errors = 0
                ev["judge_correct"] = rec["judge"].get("correct")
                ev["f1"] = rec.get("f1")
            else:
                consecutive_errors += 1
                ev["error"] = True
            yield ev
            if consecutive_errors >= _BREAKER:
                yield {"phase": "aborted", "answered": len(done),
                       "detail": (f"{consecutive_errors} questions in a row failed with an "
                                  "infrastructure error — pausing so the outage isn't scored "
                                  "as low accuracy and your budget isn't spent on empty "
                                  "answers. Every answer so far is saved; press Run again to "
                                  "resume from exactly here once the provider is back.")}
                return
        yield {"phase": "config_done", "config": config}

    records = list(by_key.values())
    report = assemble(run_id=run_id, dataset=dataset, prepared=prepared, build=build,
                      configs=configs, gold=gold, records=records,
                      answer_model=ans_model, scope=scope)
    markdown = render_markdown(report)
    await asyncio.to_thread(store.save_run, dataset, run_id, report, markdown)
    await asyncio.to_thread(store.clear_inflight, dataset, resume_key)
    # The stream (and the page) get the report WITHOUT the raw records — at 1000
    # questions those are megabytes; they live in the run JSON on disk.
    yield {"phase": "report", "run_id": run_id, "report": {**report, "records": []}}
    yield {"phase": "done", "run_id": run_id}
