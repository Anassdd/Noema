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
                  doc_titles: dict[str, str] | None = None) -> dict:
    """One question through one config; never raises — errors become a scored record.

    Questions from per-document gold (QASPER: "what dataset do THEY use?") presuppose
    their document — over a multi-doc corpus they are ambiguous, so retrieval,
    generation and judging all see a form anchored to the source document's title
    (stored as `asked`); the gold answers are untouched."""
    use_vector, use_graph = CONFIGS[config]
    q = question["question"]
    title = (doc_titles or {}).get(question.get("doc_id", ""))
    if title:
        q = f'Regarding the paper "{title}": {question["question"]}'
    rec = {"qid": question["id"], "config": config, "type": question.get("type", "factoid")}
    if title:
        rec["asked"] = q
    t0 = time.perf_counter()
    try:
        chunks = []
        if use_vector or use_graph:
            chunks, _meta = await pipeline.retrieve(
                q, domain_id=domain, k=8, use_graph=use_graph, use_vector=use_vector)
            res = await asyncio.to_thread(pipeline.grounded_answer, q, chunks, model=model)
        else:
            res = await asyncio.to_thread(pipeline.closed_book_answer, q, model=model)
        rec["answer"] = res.text or ""
        rec["usage"] = res.usage.__dict__ if res.usage else None
        # evidence is checked against the FULL retrieved texts, then the archive keeps
        # only snippets — at 1000 questions full texts would make the run file huge.
        if (use_vector or use_graph) and question.get("evidence"):
            rec["evidence_hit"] = scoring.evidence_hit(
                question["evidence"], [c.text for c in chunks])
        rec["retrieved"] = [
            {"origin": "graph" if c.chunk_id.startswith("graph:") else "vector",
             "doc_id": c.doc_id, "pages": c.pages, "text": (c.text or "")[:300]}
            for c in chunks
        ]
    except Exception as exc:  # noqa: BLE001 — a failed call is a data point, not a crash
        rec.update({"answer": "", "error": str(exc)[:300], "usage": None, "retrieved": []})
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
        golds = [q["answer"]] + [a for a in q.get("alt_answers", []) if a]
        rec["em"] = any(scoring.exact_match(rec.get("answer", ""), g) for g in golds)
        rec["f1"] = round(max(scoring.token_f1(rec.get("answer", ""), g) for g in golds), 4)
        verdict = await asyncio.to_thread(
            scoring.judge, q["question"], golds[0], rec.get("answer", ""), tuple(golds[1:]))
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
                      answer_model=old.get("answer_model", ""))
    markdown = render_markdown(report)
    await asyncio.to_thread(store.save_run, dataset, new_id, report, markdown)
    yield {"phase": "report", "run_id": new_id, "report": {**report, "records": []}}
    yield {"phase": "done", "run_id": new_id}


async def run_bench(dataset: str, configs: list[str], *,
                    extract_model: str | None = None,
                    answer_model: str | None = None) -> AsyncIterator[dict]:
    """The whole cycle as an event stream: (build once) -> answer -> score -> report."""
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
           "fingerprint": fp, "save_name": save_name, "questions": len(gold)}

    build = store.find_build(manifest, fp)
    existing = await asyncio.to_thread(saves.list_saves, "default")
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
    records: list[dict] = []
    for config in configs:
        yield {"phase": "config_start", "config": config, "questions": len(gold)}
        for i, q in enumerate(gold):
            rec = await _answer(config, q, domain, answer_model, doc_titles)
            records.append(rec)
            yield {"phase": "scored", "config": config, "i": i + 1, "total": len(gold),
                   "qid": rec["qid"], "judge_correct": rec["judge"].get("correct"),
                   "f1": rec["f1"]}
        yield {"phase": "config_done", "config": config}

    report = assemble(run_id=run_id, dataset=dataset, prepared=prepared, build=build,
                      configs=configs, gold=gold, records=records,
                      answer_model=answer_model or settings.chat_model)
    markdown = render_markdown(report)
    await asyncio.to_thread(store.save_run, dataset, run_id, report, markdown)
    # The stream (and the page) get the report WITHOUT the raw records — at 1000
    # questions those are megabytes; they live in the run JSON on disk.
    yield {"phase": "report", "run_id": run_id, "report": {**report, "records": []}}
    yield {"phase": "done", "run_id": run_id}
