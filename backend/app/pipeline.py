"""The expert answer pipeline — route → retrieve (RAG ⊕ graph, fused) → answer → verify.

Built in slices. This slice is retrieval + fusion: the graph is treated as *just another
retriever* that returns `ScoredChunk`s, and its ranking is RRF-fused with the hybrid vector
base. Fusing (not routing to one store) is the SOTA base pattern and is robust to a wrong
store choice — see NOEMA_SOTA_RESEARCH_SUMMARY.md §3–4.

Async, because the graph search is async (FalkorDriver on the app loop) while the vector
search is sync (run in a thread).
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from app import llm_client
from app.graph.manager import graph_manager
from app.retrieval import ScoredChunk, search_trace

_RRF_K = 60


def _rrf(rankings: list[list[str]], k: int = _RRF_K) -> dict[str, float]:
    """Reciprocal Rank Fusion: a chunk found high by several retrievers rises."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


def _fact_to_chunk(fact, episode_names: dict[str, str], domain_id: str) -> ScoredChunk:
    """Adapt a Graphiti fact (a relationship edge) into the shared retrieval contract, so
    it fuses and cites like any other source. Provenance = the episode it came from,
    named '<file> · p<N>' at ingestion, parsed back into doc + page."""
    doc_id, pages = "graph memory", []
    for uuid in fact.episodes:
        raw = episode_names.get(uuid)
        if not raw:
            continue
        if " · p" in raw:
            doc_id, tail = raw.rsplit(" · p", 1)
            try:
                pages = [int(tail)]
            except ValueError:
                pages = []
        else:
            doc_id = raw
        break
    text = fact.fact or f"{fact.source} — {fact.name} — {fact.target}"
    return ScoredChunk(
        chunk_id=f"graph:{fact.uuid}",
        text=text,
        context=f"{fact.source} → {fact.target}",
        doc_id=doc_id,
        pages=pages,
        section=fact.name or "",
        domain_id=domain_id,
        scores={"graph": float(fact.score or 0.0)},
    )


async def graph_chunks(query: str, *, domain_id: str = "default", limit: int = 10) -> list[ScoredChunk]:
    """Retrieve from the graph and return results as ScoredChunks (with provenance)."""
    mem = await graph_manager.get(domain_id)
    facts = await mem.search(query, limit=limit)
    if not facts:
        return []
    names = await mem.episode_names([u for f in facts for u in f.episodes])
    return [_fact_to_chunk(f, names, domain_id) for f in facts]


async def retrieve(
    query: str,
    *,
    domain_id: str = "default",
    k: int = 8,
    use_graph: bool = True,
    use_vector: bool = True,
    rerank_mode: str = "off",
    graph_limit: int = 10,
) -> tuple[list[ScoredChunk], dict]:
    """Retrieve from the vector base and the graph, RRF-fuse the two rankings, return the
    top-k plus a small meta dict (per-source counts) the runtime trace can surface."""
    rankings: list[list[str]] = []
    by_id: dict[str, ScoredChunk] = {}
    meta = {"vector": 0, "graph": 0}

    if use_vector:
        vtrace = await asyncio.to_thread(
            search_trace, query, k=max(k, 8), domain_id=domain_id, rerank_mode=rerank_mode
        )
        for c in vtrace.final:
            by_id[c.chunk_id] = c
        rankings.append([c.chunk_id for c in vtrace.final])
        meta["vector"] = len(vtrace.final)

    if use_graph:
        gchunks = await graph_chunks(query, domain_id=domain_id, limit=graph_limit)
        for c in gchunks:
            by_id.setdefault(c.chunk_id, c)
        rankings.append([c.chunk_id for c in gchunks])
        meta["graph"] = len(gchunks)

    fused = _rrf(rankings)
    for cid, s in fused.items():
        if cid in by_id:
            by_id[cid].scores["fused"] = round(s, 5)
            by_id[cid].score = round(s, 5)
    final = sorted((by_id[c] for c in fused if c in by_id), key=lambda c: c.score, reverse=True)[:k]
    meta["fused"] = len(final)
    return final, meta


# ---- the agentic answer loop ----------------------------------------------
# route (needs retrieval?) -> retrieve+fuse -> grade sufficiency (CRAG, before) ->
# grounded answer -> grade faithfulness (Self-RAG, after) -> retry (max 2) or answer.

_GROUND_SYS = (
    "Answer the user's question using the numbered sources below as your ground truth. "
    "Cite the sources you rely on inline as [S1], [S2], etc. Prefer the sources over prior "
    "knowledge; if they don't fully cover the question, answer what you can and say plainly "
    "what's missing. Answer in the question's language."
)
_ROUTE_SYS = (
    "Decide whether answering the user's latest message needs searching a document library "
    '(the knowledge base). Reply ONLY JSON: {"retrieve": true|false, "reason": "<short>"}. '
    "Retrieve for questions about facts, content, or knowledge that would live in documents. "
    "Do NOT retrieve for greetings, small talk, or meta questions about the conversation."
)
_SUFF_SYS = (
    "Grade whether the provided sources contain enough to answer the question. Reply ONLY "
    'JSON: {"enough": true|false, "reason": "<short>"}. Be strict: if the sources only '
    "tangentially touch the question, answer false."
)
_FAITH_SYS = (
    "Check whether the assistant's answer is fully supported by the sources — no invented "
    'facts, no unsupported claims. Reply ONLY JSON: {"grounded": true|false, "reason": "<short>"}.'
)


def _sources_block(chunks: list[ScoredChunk]) -> str:
    return "\n\n".join(f"[S{i + 1}] (source: {c.citation})\n{c.text}" for i, c in enumerate(chunks))


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _judge_sync(system: str, user: str) -> dict:
    """One cheap buffered LLM judgement, parsed leniently from its JSON reply."""
    res = llm_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0, max_tokens=200,
    )
    txt = (res.text or "").strip()
    try:
        return json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception:
        return {}


def _generate_sync(messages: list[dict], chunks: list[ScoredChunk], model: str | None):
    """Grounded answer, layering the sources onto the existing conversation (persona, user
    memory, history stay intact) just before the latest question."""
    grounding = {"role": "system", "content": f"{_GROUND_SYS}\n\nSources:\n{_sources_block(chunks)}"}
    convo = list(messages[:-1]) + [grounding, messages[-1]] if messages else [grounding]
    return llm_client.chat(convo, model=model, temperature=0.0)


def _stream_pieces(text: str, size: int = 44):
    for i in range(0, len(text), size):
        yield text[i: i + size]


def _sources_payload(chunks: list[ScoredChunk]) -> list[dict]:
    return [
        {
            "n": i + 1,
            "citation": c.citation,
            "doc_id": c.doc_id,
            "pages": c.pages,
            "section": c.section,
            "text": c.text,
            "origin": "graph" if c.chunk_id.startswith("graph:") else "vector",
            "score": c.score,
        }
        for i, c in enumerate(chunks)
    ]


async def answer_stream(
    messages: list[dict], *, model: str | None = None, domain_id: str = "default",
    memory: str | None = None, max_tries: int = 2,
) -> AsyncIterator[dict]:
    """Drive the whole expert loop, yielding event dicts:
      {"type":"status", stage, detail}  — the live runtime trace
      {"type":"delta", text}            — answer pieces
      {"type":"sources", sources:[...]} — what the answer is grounded on
      {"type":"usage", usage}           — token counts

    `memory` selects a saved snapshot to answer from (its graph + RAG); None = live memory.
    """
    if memory:
        from app.saves import save_key
        domain_id = save_key(domain_id, memory)  # retrieve from the saved snapshot's stores
    query = _last_user(messages)

    yield {"type": "status", "stage": "routing", "detail": "Deciding if this needs the knowledge base…"}
    j = await asyncio.to_thread(_judge_sync, _ROUTE_SYS, query)
    need = bool(j.get("retrieve", True))  # fail open to grounding

    if not need:
        yield {"type": "status", "stage": "direct", "detail": "Answering directly — no retrieval needed"}
        res = await asyncio.to_thread(lambda: llm_client.chat(messages, model=model))
        for piece in _stream_pieces(res.text or ""):
            yield {"type": "delta", "text": piece}
        yield {"type": "usage", "usage": res.usage.__dict__ if res.usage else None}
        return

    yield {"type": "status", "stage": "route", "detail": "This needs the knowledge base"}

    final_chunks: list[ScoredChunk] = []
    answer_text, usage, grounded, covered = "", None, True, True

    for attempt in range(1, max_tries + 1):
        detail = "Searching the vector base + graph…" if attempt == 1 else "Retrieving more and re-fusing…"
        yield {"type": "status", "stage": "retrieving", "detail": detail}
        chunks, meta = await retrieve(query, domain_id=domain_id, k=8 * attempt)
        final_chunks = chunks
        yield {"type": "status", "stage": "retrieved",
               "detail": f"{meta['fused']} sources · {meta['vector']} vector · {meta['graph']} graph"}

        if not chunks:
            covered = False
            if attempt < max_tries:
                yield {"type": "status", "stage": "redoing", "detail": "Nothing found — widening the search…"}
                continue
            break

        yield {"type": "status", "stage": "grading", "detail": "Checking the sources cover the question…"}
        js = await asyncio.to_thread(_judge_sync, _SUFF_SYS, f"Question: {query}\n\nSources:\n{_sources_block(chunks)}")
        enough = bool(js.get("enough", True))
        if not enough and attempt < max_tries:
            covered = False
            yield {"type": "status", "stage": "insufficient",
                   "detail": js.get("reason") or "Sources look thin — retrieving more…"}
            continue
        covered = enough

        yield {"type": "status", "stage": "answering", "detail": "Composing a grounded answer…"}
        res = await asyncio.to_thread(_generate_sync, messages, chunks, model)
        answer_text, usage = res.text or "", res.usage

        yield {"type": "status", "stage": "verifying", "detail": "Checking the answer is grounded in the sources…"}
        jf = await asyncio.to_thread(
            _judge_sync, _FAITH_SYS,
            f"Question: {query}\n\nSources:\n{_sources_block(chunks)}\n\nAnswer:\n{answer_text}")
        grounded = bool(jf.get("grounded", True))
        if grounded or attempt == max_tries:
            yield {"type": "status", "stage": "grounded" if grounded else "ungrounded",
                   "detail": "Grounded in the sources ✓" if grounded else "Couldn't fully verify — answering with a caveat"}
            break
        yield {"type": "status", "stage": "redoing", "detail": "Answer wasn't fully grounded — retrieving more and retrying…"}

    if not final_chunks:
        answer_text = "I couldn't find anything in the indexed documents to answer that."
        yield {"type": "status", "stage": "empty", "detail": "No matching sources in the memory"}

    for piece in _stream_pieces(answer_text):
        yield {"type": "delta", "text": piece}
    yield {"type": "sources", "sources": _sources_payload(final_chunks)}
    yield {"type": "usage", "usage": usage.__dict__ if usage else None}
