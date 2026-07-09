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

from app import beliefs, llm_client
from app.graph.manager import graph_manager
from app.retrieval import ScoredChunk, rrf, search_trace


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


async def graph_chunks(query: str, *, domain_id: str = "default", limit: int = 10,
                       doc_id: str | None = None) -> list[ScoredChunk]:
    """Retrieve from the graph and return results as ScoredChunks (with provenance).

    A graph fact's source document is only known after it's mapped to a chunk (its episode
    name carries the doc). To scope to one document we over-retrieve, then keep only that
    document's facts — so a per-document question can't surface another document's facts."""
    mem = await graph_manager.get(domain_id)
    facts = await mem.search(query, limit=max(limit * 6, 60) if doc_id else limit)
    if not facts:
        return []
    names = await mem.episode_names([u for f in facts for u in f.episodes])
    chunks = [_fact_to_chunk(f, names, domain_id) for f in facts]
    if doc_id:
        chunks = [c for c in chunks if c.doc_id == doc_id][:limit]
    return chunks


async def retrieve(
    query: str,
    *,
    domain_id: str = "default",
    k: int = 8,
    use_graph: bool = True,
    use_vector: bool = True,
    rerank_mode: str = "off",
    graph_limit: int = 10,
    doc_id: str | None = None,
) -> tuple[list[ScoredChunk], dict]:
    """Retrieve from the vector base and the graph, RRF-fuse the two rankings, return the
    top-k plus a small meta dict (per-source counts) the runtime trace can surface.

    `doc_id` scopes both retrievers to one source document — for per-document benchmarks
    (e.g. QASPER) whose questions presuppose their paper."""
    rankings: list[list[str]] = []
    by_id: dict[str, ScoredChunk] = {}
    meta = {"vector": 0, "graph": 0}

    if use_vector:
        vtrace = await asyncio.to_thread(
            search_trace, query, k=max(k, 8), domain_id=domain_id, rerank_mode=rerank_mode,
            doc_id=doc_id,
        )
        for c in vtrace.final:
            by_id[c.chunk_id] = c
        rankings.append([c.chunk_id for c in vtrace.final])
        meta["vector"] = len(vtrace.final)

    if use_graph:
        gchunks = await graph_chunks(query, domain_id=domain_id, limit=graph_limit, doc_id=doc_id)
        for c in gchunks:
            by_id.setdefault(c.chunk_id, c)
        rankings.append([c.chunk_id for c in gchunks])
        meta["graph"] = len(gchunks)

    fused = rrf(rankings)
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
    "what's missing. If the user's own notes are provided separately and disagree with the "
    "sources, surface both and attribute each — do not silently pick. Answer in the "
    "question's language."
)
# The user's own beliefs about this memory context (see app/beliefs.py). Injected as a
# distinct block so the answer keeps them apart from the retrieved corpus and can say
# "the sources say X, while your own note holds Y" when they conflict.
_BELIEFS_SYS = (
    "Below are the USER'S OWN notes and beliefs about this topic. Treat them as the user's "
    "personal opinion — not established fact, and not one of the numbered sources. When the "
    "user's notes and the sources disagree, do NOT merge them or silently choose one: present "
    "BOTH and attribute each clearly (e.g. \"the sources indicate…, while your own note "
    "holds…\"). If they are irrelevant to the question, ignore them."
)
# Cleans a /note before saving: resolve references against the recent chat so the note stands
# alone, WITHOUT changing the claim. The "even if you believe it is wrong" clause is load-bearing
# — the user may be asserting a belief that contradicts the corpus on purpose; we must not "fix" it.
_NOTE_SYS = (
    "You clean up a note the user is saving to their personal notes, using the recent conversation "
    "only for context. Do EXACTLY these two things and nothing else:\n"
    "1. Resolve pronouns and references (he/she/it/they/this/that/the former/etc.) into the explicit "
    "entity from the conversation, so the note stands on its own.\n"
    "2. Remove leading filler such as 'that', 'note that', 'remember that', 'add that'.\n"
    "Do NOT fact-check, correct, reword, translate, summarize, or change the meaning or opinion in "
    "ANY way — even if you believe it is wrong. Keep the user's exact claim and language. If nothing "
    "needs resolving, return it unchanged.\n"
    'Reply ONLY JSON: {"note": "<the cleaned note>"}.'
)
# One call does two jobs, so a follow-up never loses the thread and we add no round-trip:
# (1) rewrite the latest message into a STANDALONE query by resolving references against the
# recent turns — language-agnostic, the model decides, no pronoun lists; (2) route it. The
# rewrite is used for search only; the answer is still generated on the real conversation.
_ROUTE_SYS = (
    "You prepare a user's latest message for retrieval in a chat assistant. Given the recent "
    "conversation and the latest message, do two things:\n"
    "1. Rewrite the latest message into a STANDALONE query: resolve pronouns, ellipsis and "
    "follow-up references (\"him\", \"that\", \"and its causes?\", \"why\") into the explicit "
    "entities from the conversation, so the query is self-contained and searchable on its own. "
    "If the message is already self-contained, return it unchanged. Keep it in the SAME "
    "LANGUAGE as the latest message. Do not answer it — only rewrite it.\n"
    "2. Decide whether answering it needs searching a document library (the knowledge base). "
    "Retrieve for questions about facts, content, or knowledge that would live in documents; "
    "do NOT retrieve for greetings, small talk, or meta questions about the conversation.\n"
    'Reply ONLY JSON: {"standalone": "<rewritten query>", "retrieve": true|false}.'
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


def _recent_context(messages: list[dict], *, max_turns: int = 6, clip: int = 400,
                    drop_last: bool = True) -> str:
    """The last few turns compacted, so a reference can be resolved against them. Capped
    (turns + per-message length) to stay cheap; empty when there's nothing prior. `drop_last`
    skips the final message (the current question) for the query path; pass False when the
    text to resolve is NOT already in `messages` (e.g. a /note typed after the last turn)."""
    src = messages[:-1] if drop_last else messages
    lines = []
    for m in src[-max_turns:]:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = " ".join((m.get("content") or "").split())
        if len(text) > clip:
            text = text[:clip] + "…"
        if text:
            lines.append(f"{'User' if role == 'user' else 'Assistant'}: {text}")
    return "\n".join(lines)


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


def contextualize_note(note: str, messages: list[dict]) -> str:
    """Make a /note stand alone: resolve references against the recent chat and strip leading
    filler, WITHOUT altering the claim (see _NOTE_SYS). Fails open to the raw note — cleanup must
    never block or distort saving. No chat context → nothing to resolve → verbatim."""
    note = " ".join((note or "").split())
    if not note:
        return note
    ctx = _recent_context(messages, drop_last=False)  # the note isn't in `messages`
    if not ctx:
        return note
    j = _judge_sync(_NOTE_SYS, f"Recent conversation:\n{ctx}\n\nNote to clean: {note}")
    cleaned = (j.get("note") or "").strip()
    return cleaned or note


def _beliefs_msg(beliefs_text: str) -> dict:
    return {"role": "system", "content": f"{_BELIEFS_SYS}\n\nThe user's notes:\n{beliefs_text}"}


def _generate_sync(messages: list[dict], chunks: list[ScoredChunk], model: str | None,
                   beliefs_text: str = ""):
    """Grounded answer, layering the sources (and the user's own notes, if any) onto the
    existing conversation (persona, user memory, history stay intact) just before the latest
    question."""
    blocks = []
    if beliefs_text:
        blocks.append(_beliefs_msg(beliefs_text))
    blocks.append({"role": "system", "content": f"{_GROUND_SYS}\n\nSources:\n{_sources_block(chunks)}"})
    convo = list(messages[:-1]) + blocks + [messages[-1]] if messages else blocks
    return llm_client.chat(convo, model=model, temperature=0.0)


def grounded_answer(question: str, chunks: list[ScoredChunk], *, model: str | None = None):
    """One deterministic grounded answer to a standalone question — retrieval already
    done, no routing/CRAG/verify loop. This is the bench's answer path: every config
    gets the identical generation step, so only retrieval differs. Returns ChatResult."""
    return _generate_sync([{"role": "user", "content": question}], chunks, model)


def closed_book_answer(question: str, *, model: str | None = None):
    """The bench's contamination-floor config: the same generator, NO sources. What it
    scores is what the model already knew — every method's lift is measured above this."""
    return llm_client.chat(
        [{"role": "user", "content": question}], model=model, temperature=0.0
    )


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
    memory: str | None = None, retrieval: str = "hybrid", max_tries: int = 2,
) -> AsyncIterator[dict]:
    """Drive the whole expert loop, yielding event dicts:
      {"type":"status", stage, detail}  — the live runtime trace
      {"type":"delta", text}            — answer pieces
      {"type":"sources", sources:[...]} — what the answer is grounded on
      {"type":"usage", usage}           — token counts

    `memory` selects a saved snapshot to answer from (its graph + RAG); None = live memory.
    `retrieval` selects which store answers — "hybrid" (both, fused), "rag" (contextual
    vector base only) or "graph" (knowledge graph only) — so methods can be compared live.
    """
    use_vector = retrieval != "graph"
    use_graph = retrieval != "rag"
    # The user's own notes for THIS memory context (the selected save, else the live domain).
    # Read before domain_id is swapped for the save key — beliefs are keyed by the context the
    # user picks, not by the snapshot's internal store name.
    belief_text = await asyncio.to_thread(beliefs.read_beliefs, domain_id, memory)
    if memory:
        from app.saves import save_key
        domain_id = save_key(domain_id, memory)  # retrieve from the saved snapshot's stores
    query = _last_user(messages)

    yield {"type": "status", "stage": "routing", "detail": "Reading the question in context…"}
    context = _recent_context(messages)
    route_input = f"Recent conversation:\n{context}\n\nLatest message: {query}" if context else query
    j = await asyncio.to_thread(_judge_sync, _ROUTE_SYS, route_input)
    search_query = (j.get("standalone") or "").strip() or query  # fail open to the raw message
    need = bool(j.get("retrieve", True))  # fail open to grounding

    if context and search_query.strip().lower() != query.strip().lower():
        yield {"type": "status", "stage": "contextualized", "detail": f"Understood as: “{search_query}”"}

    if belief_text:
        yield {"type": "status", "stage": "beliefs", "detail": "Weighing your own notes alongside the answer"}

    if not need:
        yield {"type": "status", "stage": "direct", "detail": "Answering directly — no retrieval needed"}
        convo = messages
        if belief_text and messages:
            convo = list(messages[:-1]) + [_beliefs_msg(belief_text)] + [messages[-1]]
        res = await asyncio.to_thread(lambda: llm_client.chat(convo, model=model))
        for piece in _stream_pieces(res.text or ""):
            yield {"type": "delta", "text": piece}
        yield {"type": "usage", "usage": res.usage.__dict__ if res.usage else None}
        return

    yield {"type": "status", "stage": "route", "detail": "This needs the knowledge base"}

    final_chunks: list[ScoredChunk] = []
    answer_text, usage, grounded, covered = "", None, True, True

    stores = {"hybrid": "vector base + graph", "rag": "vector base only", "graph": "graph only"}
    for attempt in range(1, max_tries + 1):
        detail = (f"Searching the {stores.get(retrieval, 'vector base + graph')}…"
                  if attempt == 1 else "Retrieving more and re-fusing…")
        yield {"type": "status", "stage": "retrieving", "detail": detail}
        chunks, meta = await retrieve(search_query, domain_id=domain_id, k=8 * attempt,
                                      use_graph=use_graph, use_vector=use_vector)
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
        js = await asyncio.to_thread(_judge_sync, _SUFF_SYS, f"Question: {search_query}\n\nSources:\n{_sources_block(chunks)}")
        enough = bool(js.get("enough", True))
        if not enough and attempt < max_tries:
            covered = False
            yield {"type": "status", "stage": "insufficient",
                   "detail": js.get("reason") or "Sources look thin — retrieving more…"}
            continue
        covered = enough

        yield {"type": "status", "stage": "answering", "detail": "Composing a grounded answer…"}
        res = await asyncio.to_thread(_generate_sync, messages, chunks, model, belief_text)
        answer_text, usage = res.text or "", res.usage

        yield {"type": "status", "stage": "verifying", "detail": "Checking the answer is grounded in the sources…"}
        jf = await asyncio.to_thread(
            _judge_sync, _FAITH_SYS,
            f"Question: {search_query}\n\nSources:\n{_sources_block(chunks)}\n\nAnswer:\n{answer_text}")
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
