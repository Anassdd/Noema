"""Pre-run cost estimation — honest ballparks shown BEFORE any money moves.

The model: graph extraction pushes ~21× the corpus tokens through the extractor
(+ ~4× out), blurbs ~5× through the chat model, embeddings ~1.2×; queries cost
per question per config. Treat every figure as ±2× until the first real build
calibrates it against the provider dashboard.
"""

from __future__ import annotations

import os

from app import saves
from app.bench import store
from app.config import settings

# The contextualizer chunks each doc to ~512 tokens and, per chunk, resends the WHOLE
# document as a cacheable prefix (see retrieval/contextual.py). So its cost scales with
# chunk_count × doc_tokens, NOT a flat multiple of the corpus — the old 5× model
# under-counted a 50k-token doc by ~9×. Cached prefix tokens are billed at a discount.
_CHUNK_TOKENS = 512
_BLURB_OUT_TOKENS = 45
_CACHE_DISCOUNT = float(os.getenv("BENCH_CACHE_DISCOUNT", "0.5"))  # cached input billed fraction

# $ per 1M tokens (input, output) — matched by prefix so snapshots resolve too.
PRICES = {
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-4.1-mini": (0.40, 1.60),
}
EMBED_PRICES = {"text-embedding-3-large": 0.13, "text-embedding-3-small": 0.02}
_FALLBACK = (0.75, 4.50)  # unknown model -> assume mini-tier


def _price(model: str) -> tuple[float, float]:
    return next((p for k, p in PRICES.items() if model.startswith(k)), _FALLBACK)


def estimate(dataset: str, configs: list[str], extract_model: str | None = None) -> dict:
    from app.bench.runner import CONFIGS, _fingerprint, _resolve_extract_model

    manifest = store.load_manifest(dataset)
    prepared = manifest.get("prepared")
    if not prepared:
        return {"ready": False, "reason": "not prepared"}
    n_q = sum(1 for q in store.load_gold(dataset) if q.get("status") == "approved")

    extract = _resolve_extract_model(extract_model)
    fp = _fingerprint(prepared["corpus_hash"], prepared["cap_tokens"], extract)
    save_name = f"bench-{dataset}-{prepared['cap_tokens'] // 1000}k-{fp[:6]}"
    build_exists = (store.find_build(manifest, fp) is not None
                    and save_name in saves.list_saves("default"))

    # An interrupted build resumes: count what survived (both layers), bill only
    # the remainder — extraction scales by remaining episodes, blurbs by docs.
    resumable, expected_eps = 0, None
    rag_done, rag_total = 0, prepared["docs"]
    if not build_exists and save_name in saves.list_saves("default"):
        from app.graph.server import falkor_ops
        from app.retrieval import VectorStore

        domain = saves.save_key("default", save_name)

        def _episodes(db):
            if domain not in db.list_graphs():
                return 0
            return db.select_graph(domain).query(
                "MATCH (e:Episodic) RETURN count(e)").result_set[0][0]

        resumable = falkor_ops(_episodes)
        rag_done = len(VectorStore(domain).doc_ids())
        if resumable or rag_done:
            from app.bench.datasets import split_windows
            from app.bench.runner import EPISODE_TOKENS
            expected_eps = sum(len(split_windows(d["text"], EPISODE_TOKENS))
                               for d in store.load_corpus(dataset))

    ep_frac = max(0.0, 1 - resumable / expected_eps) if expected_eps else 1.0
    doc_frac = max(0.0, 1 - rag_done / rag_total) if rag_total else 1.0

    t = prepared["tokens"] / 1e6
    ein, eout = _price(extract)
    cin, cout = _price(settings.chat_model)
    build = 0.0
    build_breakdown = {}
    if not build_exists:
        # Contextualization: per doc, chunk_count × (whole doc as a mostly-cached prefix).
        ctx_in = ctx_out = 0.0
        for d in store.load_corpus(dataset):
            doc_tokens = d.get("tokens", 0)
            chunks = max(1, -(-doc_tokens // _CHUNK_TOKENS))  # ceil
            uncached = doc_tokens + chunks * (_CHUNK_TOKENS + 70)  # first doc pass + per-call chunk+instr
            cached = max(0, chunks - 1) * doc_tokens              # repeated doc prefix, cached
            ctx_in += uncached + cached * _CACHE_DISCOUNT
            ctx_out += chunks * _BLURB_OUT_TOKENS
        contextualization = (ctx_in * cin + ctx_out * cout) / 1e6 * doc_frac
        # Graph extraction (Graphiti-internal LLM calls, not metered by us): ~21× corpus in,
        # ~4× out — the one term still uncalibrated, hence the wide caveat below.
        extraction = (21 * t * ein + 4 * t * eout) * ep_frac
        embeddings = 1.2 * t * EMBED_PRICES.get(settings.embed_model, 0.13) * doc_frac
        build = contextualization + extraction + embeddings
        build_breakdown = {"contextualization_usd": round(contextualization, 2),
                           "graph_extraction_usd": round(extraction, 2),
                           "embeddings_usd": round(embeddings, 3)}

    configs = [c for c in configs if c in CONFIGS] or list(CONFIGS)
    # Query costs calibrated to the measured qasper-train run (rag ≈ 2.4k tok/q, not 8k).
    per_q_retrieval = (2600 * cin + 300 * cout) / 1e6
    per_q_closed = (300 * cin + 250 * cout) / 1e6
    answers = sum(n_q * (per_q_closed if c == "closed_book" else per_q_retrieval)
                  for c in configs)
    judge_free = bool(settings.judge_base_url and settings.judge_model
                      and settings.judge_api_key)
    judging = 0.0 if judge_free else n_q * len(configs) * (400 * cin + 60 * cout) / 1e6

    # Query wall-clock is dominated by the judge throttle (JUDGE_RPM, default 9/min when a
    # judge endpoint is configured) — hundreds of paced verdicts, not the generations.
    rpm = float(os.getenv("JUDGE_RPM", "9" if judge_free else "0"))
    verdicts = n_q * len(configs)
    judge_minutes = round(verdicts / rpm) if rpm > 0 else 0

    unpriced = sorted({m for m in (extract, settings.chat_model)
                       if not any(m.startswith(k) for k in PRICES)})

    return {
        "ready": True,
        "build_exists": build_exists,
        "build_partial": bool(resumable or rag_done),
        "resumable_episodes": resumable,
        "expected_episodes": expected_eps,
        "rag_done": rag_done,
        "rag_total": rag_total,
        "save_name": save_name,
        "extract_model": extract,
        "questions": n_q,
        "build_usd": round(build, 2),
        "build_breakdown": build_breakdown,
        "queries_usd": round(answers + judging, 2),
        "total_usd": round(build + answers + judging, 2),
        "judge_free": judge_free,
        "judge_minutes": judge_minutes,
        # Unknown model names silently priced at mini-tier — surfaced so a prod (llmaas)
        # model isn't gated by a made-up number.
        "unpriced_models": unpriced,
        "build_minutes": 0 if build_exists else round(
            prepared["tokens"] / 700 * 22 / 60 * ep_frac),
    }
