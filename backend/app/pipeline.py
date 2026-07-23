"""The expert answer pipeline — route → retrieve (RAG + graph supplement) → answer → verify.

Fusion design, learned the hard way: cross-store RRF between the vector base and the graph
is degenerate — their ids never overlap, so "fusion" collapses into a fixed 50/50 interleave
where one-line graph facts displace evidence-bearing chunks (measured on QASPER: evidence
recall 0.89 → 0.43, five rag-correct answers broken, zero rescued). So hybrid now keeps the
vector top-k INTACT and appends graph facts as a novelty-gated supplement: a fact gets in
only if it brings content the chunks don't already cover. The graph can add, never displace.

Async, because the graph search is async (FalkorDriver on the app loop) while the vector
search is sync (run in a thread).
"""

from __future__ import annotations

import asyncio
import json
import string
import time
from typing import AsyncIterator

from app import beliefs, llm_client
from app.config import settings
from app.graph.manager import graph_manager
from app.retrieval import ScoredChunk, VectorStore, search_trace


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
        score=float(fact.score or 0.0),
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


def _provenance(file_path: str) -> tuple[str, list[int]]:
    """Parse LightRAG's file_path back into doc + page. We ingest pieces named
    '<file> · p<N>'; entities/relations that span pieces join paths with <SEP> —
    take the first. Empty/unknown paths fall back to a generic label."""
    first = (file_path or "").split("<SEP>")[0].strip()
    if not first or first == "unknown_source":
        return "lightrag memory", []
    if " · p" in first:
        doc_id, tail = first.rsplit(" · p", 1)
        try:
            return doc_id, [int(tail)]
        except ValueError:
            return doc_id, []
    return first, []


async def lightrag_chunks(query: str, *, domain_id: str = "default",
                          limit: int = 10, doc_id: str | None = None) -> list[ScoredChunk]:
    """Retrieve from the LightRAG store and adapt to the shared retrieval contract.
    LightRAG returns relationship facts AND text chunks, both ranked; the chunks are
    the citable evidence, so they fill most of the budget and a few top facts ride
    along for the graph-level signal.

    LightRAG has no native document filter, so scoping to one `doc_id` (per-document
    benchmarks) over-retrieves and keeps only items whose file_path provenance parses
    back to that document — same trick as graph_chunks."""
    from app.lightrag.manager import lightrag_manager

    mem = await lightrag_manager.get(domain_id)
    found = await mem.search(query, limit=limit * 4 if doc_id else limit)
    relations, chunks = found["relations"], found["chunks"]
    if doc_id:
        relations = [r for r in relations if _provenance(r["file_path"])[0] == doc_id]
        chunks = [c for c in chunks if _provenance(c["file_path"])[0] == doc_id]
    out: list[ScoredChunk] = []
    for r in relations[: max(1, limit // 3)]:
        r_doc, pages = _provenance(r["file_path"])
        out.append(ScoredChunk(
            chunk_id=f"lightrag:rel:{r['source']}->{r['target']}",
            text=r["text"] or f"{r['source']} — {r['keywords']} — {r['target']}",
            context=f"{r['source']} → {r['target']}",
            doc_id=r_doc,
            pages=pages,
            section=r["keywords"],
            domain_id=domain_id,
            scores={"lightrag": 1.0},
        ))
    for c in chunks:
        if len(out) >= limit:
            break
        c_doc, pages = _provenance(c["file_path"])
        out.append(ScoredChunk(
            chunk_id=f"lightrag:{c['id']}",
            text=c["text"],
            context="",
            doc_id=c_doc,
            pages=pages,
            section="",
            domain_id=domain_id,
            scores={"lightrag": 1.0},
        ))
    return out


# Function words ignored when measuring what content a chunk/fact carries (English +
# the French the corpus speaks). Small on purpose: it only feeds the novelty gate.
_STOP = frozenset(
    "a an the of to in on for and or is are was were be been with as at by from that this "
    "these those it its their they we you which who what when where why how not no but if "
    "than then so such can could may might will would shall should must do does did has "
    "have had more most some any all each into over under between within also using used "
    "le la les un une des de du et à que pour dans sur est sont avec par ce cette ces au "
    "aux ne pas plus".split())


def _content_words(text: str) -> set[str]:
    text = (text or "").lower().translate(str.maketrans("", "", string.punctuation))
    return {w for w in text.split() if w not in _STOP and len(w) > 2}


def _novel_facts(chunks: list[ScoredChunk], facts: list[ScoredChunk],
                 budget: int, min_novelty: float = 0.3) -> list[ScoredChunk]:
    """The graph facts worth ADDING to the chunks: taken in relevance order, a fact is kept
    only if enough of its content words aren't already covered by the chunks (and the facts
    already kept). A fact restating what a chunk says adds distraction, not knowledge; a
    fact bridging entities the chunks miss is exactly the cross-document signal a graph is
    for. Adaptive by construction — anywhere from 0 to `budget` facts get in."""
    covered = _content_words(" ".join(c.text for c in chunks))
    picked: list[ScoredChunk] = []
    for fact in facts:
        words = _content_words(fact.text)
        if not words:
            continue
        if len(words - covered) / len(words) < min_novelty:
            continue
        picked.append(fact)
        covered |= words
        if len(picked) >= budget:
            break
    return picked


# Retrieval profiles per question type — the router's typed guess picks one; a failed
# sufficiency check escalates to the next (see _escalate). Budgets only SHIFT between
# chunks and graph — both stores always run, so a misrouted question degrades, never breaks.
PROFILES = {
    "factoid": {"k": 8, "facts": 8, "graph_limit": 10},
    "relational": {"k": 6, "facts": 8, "graph_limit": 20},
    "global": {"k": 4, "facts": 12, "graph_limit": 30},
}
_LADDER = ("factoid", "relational", "global")


def _escalate(qtype: str, steps: int) -> str:
    """The retry ladder: each failed attempt climbs one profile toward global."""
    start = _LADDER.index(qtype) if qtype in _LADDER else 0
    return _LADDER[min(start + steps, len(_LADDER) - 1)]


# The router's corpus map — a ~200-token standing summary of what this memory holds
# (document names + most-connected entities), so "compare A and B" can be classified
# as same-document or cross-document. Cached per domain; failures degrade to "".
_MAP_TTL_S = 300
_map_cache: dict[str, tuple[float, str]] = {}


async def _corpus_map(domain_id: str) -> str:
    cached = _map_cache.get(domain_id)
    if cached and time.monotonic() - cached[0] < _MAP_TTL_S:
        return cached[1]
    try:
        docs = await asyncio.to_thread(lambda: sorted(VectorStore(domain_id).doc_ids()))
    except Exception:
        docs = []
    try:
        mem = await graph_manager.get(domain_id)
        entities = await mem.top_entities(15)
    except Exception:
        entities = []
    parts = []
    if docs:
        parts.append("Documents in the knowledge base: " + ", ".join(docs[:15])
                     + (" …" if len(docs) > 15 else "") + ".")
    if entities:
        parts.append("Key entities: " + ", ".join(entities) + ".")
    text = " ".join(parts)
    _map_cache[domain_id] = (time.monotonic(), text)
    return text


async def retrieve(
    query: str,
    *,
    domain_id: str = "default",
    k: int = 8,
    use_graph: bool = True,
    use_vector: bool = True,
    use_lightrag: bool = False,
    rerank_mode: str | None = None,
    graph_limit: int = 10,
    max_facts: int | None = None,
    doc_id: str | None = None,
) -> tuple[list[ScoredChunk], dict]:
    """Retrieve the context for one question, plus a small meta dict (per-source counts)
    the runtime trace can surface.

    Hybrid (vector + graph) is SUPPLEMENT fusion: the vector top-k — the evidence backbone,
    identical to what rag-alone returns — plus up to k novelty-gated graph facts appended
    at the end. Two stronger graph roles were tried and MEASURED WORSE on QASPER, both by
    displacing query-relevant chunks: cross-store RRF (fixed interleave: acc 0.59, broke
    5/rescued 0 vs rag) and graph-corroborated promotion into the tail slots (acc 0.61 vs
    0.74, evidence recall 0.89→0.83 — fact-adjacent ≠ question-relevant). The graph earns
    its keep as added facts, not as a chunk-ranking signal.

    `use_lightrag` alone swaps in the LightRAG strategy as the retriever — a
    self-contained method (own graph + own vectors). Combined with `use_vector` it
    becomes the supplement store under the SAME fusion contract as the graph: the
    vector top-k stays identical to rag-alone, LightRAG items only append through
    the novelty gate (the bench's lightrag_hybrid config).

    `rerank_mode` None = the configured default (RETRIEVAL_RERANK, "llm" unless overridden):
    one cheap listwise call re-reads the fused candidate pool against the question before
    the top-k cut. `max_facts` caps the graph supplement (None = k, the 8+8 default).

    `doc_id` scopes every retriever to one source document — for per-document benchmarks
    (e.g. QASPER) whose questions presuppose their paper."""
    if use_lightrag and not use_vector:
        lchunks = await lightrag_chunks(query, domain_id=domain_id, limit=max(k, 8),
                                        doc_id=doc_id)
        final = lchunks[:k]
        return final, {"vector": 0, "graph": 0, "lightrag": len(lchunks), "fused": len(final)}

    rerank = rerank_mode if rerank_mode is not None else settings.retrieval_rerank
    vchunks: list[ScoredChunk] = []
    supplements: list[ScoredChunk] = []
    supp_key = "graph" if use_graph else "lightrag"
    if use_vector:
        vtrace = await asyncio.to_thread(
            search_trace, query, k=max(k, 8), domain_id=domain_id, rerank_mode=rerank,
            doc_id=doc_id,
        )
        vchunks = vtrace.final
    if use_graph:
        supplements = await graph_chunks(query, domain_id=domain_id, limit=graph_limit,
                                         doc_id=doc_id)
    elif use_lightrag:
        supplements = await lightrag_chunks(query, domain_id=domain_id, limit=graph_limit,
                                            doc_id=doc_id)

    meta = {"vector": len(vchunks), "graph": 0, "lightrag": 0}
    if vchunks and supplements:
        facts = _novel_facts(vchunks[:k], supplements,
                             budget=max_facts if max_facts is not None else k)
        final = vchunks[:k] + facts
        meta[supp_key] = len(facts)
        meta[f"{supp_key}_candidates"] = len(supplements)
    elif vchunks:
        final = vchunks[:k]
    else:
        final = supplements[:k]
        meta[supp_key] = len(final)
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
    "language the question is WRITTEN in — judged by its words alone, never inferred "
    "from names, nationalities or topics; if unclear, answer in English."
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
    "3. Classify the question's retrieval TYPE, using the knowledge-base map when given:\n"
    '   "factoid"    — asks one fact, value or definition that likely sits in one passage.\n'
    '   "relational" — asks to connect, compare or trace across entities or documents.\n'
    '   "global"     — asks about themes, patterns, or the corpus as a whole.\n'
    'Reply ONLY JSON: {"standalone": "<rewritten query>", "retrieve": true|false, '
    '"type": "factoid"|"relational"|"global"}.'
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
    """One cheap buffered LLM judgement, parsed leniently from its JSON reply.
    The cap is generous on purpose: max_tokens only bounds the worst case, it never
    adds cost — and the route reply embeds the rewritten query, which a tight cap
    would truncate into a parse failure (silently degrading to the raw query)."""
    res = llm_client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0, max_tokens=400,
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
                   effort: str | None = None,
                   beliefs_text: str = ""):
    """Grounded answer, layering the sources (and the user's own notes, if any) onto the
    existing conversation (persona, user memory, history stay intact) just before the latest
    question."""
    blocks = []
    if beliefs_text:
        blocks.append(_beliefs_msg(beliefs_text))
    blocks.append({"role": "system", "content": f"{_GROUND_SYS}\n\nSources:\n{_sources_block(chunks)}"})
    convo = list(messages[:-1]) + blocks + [messages[-1]] if messages else blocks
    return llm_client.chat(convo, model=model, temperature=0.0,
                           reasoning=effort or settings.chat_reasoning)


def grounded_answer(question: str, chunks: list[ScoredChunk], *, model: str | None = None,
                    effort: str | None = None):
    """One deterministic grounded answer to a standalone question — retrieval already
    done, no routing/CRAG/verify loop. This is the bench's answer path: every config
    gets the identical generation step, so only retrieval differs. Returns ChatResult."""
    return _generate_sync([{"role": "user", "content": question}], chunks, model, effort)


def closed_book_answer(question: str, *, model: str | None = None,
                       effort: str | None = None):
    """The bench's contamination-floor config: the same generator, NO sources. What it
    scores is what the model already knew — every method's lift is measured above this."""
    return llm_client.chat(
        [{"role": "user", "content": question}], model=model, temperature=0.0,
        reasoning=effort or settings.chat_reasoning,
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
            "origin": ("lightrag" if c.chunk_id.startswith("lightrag:")
                       else "graph" if c.chunk_id.startswith("graph:") else "vector"),
            "score": c.score,
        }
        for i, c in enumerate(chunks)
    ]


async def web_answer_stream(messages: list[dict], *,
                            model: str | None = None) -> AsyncIterator[dict]:
    """The web retrieval mode: one provider-side web-searched answer (see
    llm_client.web_chat), streamed in the same event shapes as the expert loop.
    Deliberately outside the expert pipeline — no corpus, no CRAG/Self-RAG (there
    are no local sources to grade against), and NEVER reachable from the bench:
    only the chat route maps retrieval="web" here."""
    if not settings.web_search:
        yield {"type": "status", "stage": "error",
               "detail": "Web search is off on this deployment — set WEB_SEARCH=on "
                         "in .env (and restart) to try it."}
        return
    yield {"type": "status", "stage": "web", "detail": "searching the web…"}
    try:
        text, citations, usage = await asyncio.to_thread(
            llm_client.web_chat, messages, model=model)
    except RuntimeError as exc:
        yield {"type": "status", "stage": "error", "detail": str(exc)}
        return
    yield {"type": "delta", "text": text}
    if citations:
        yield {"type": "sources", "sources": [
            {"n": i + 1, "citation": c["title"], "text": c["url"], "origin": "web"}
            for i, c in enumerate(citations)]}
    yield {"type": "usage", "usage": usage}


async def answer_stream(
    messages: list[dict], *, model: str | None = None, domain_id: str = "default",
    memory: str | None = None, retrieval: str = "hybrid", max_tries: int = 2,
    user: str = "default", effort: str | None = None,
) -> AsyncIterator[dict]:
    """Drive the whole expert loop, yielding event dicts:
      {"type":"status", stage, detail}  — the live runtime trace
      {"type":"delta", text}            — answer pieces
      {"type":"sources", sources:[...]} — what the answer is grounded on
      {"type":"usage", usage}           — token counts

    `memory` selects a saved snapshot to answer from (its graph + RAG); None = live memory.
    `retrieval` selects which store answers — "hybrid" (both, fused), "rag" (contextual
    vector base only), "graph" (knowledge graph only) or "lightrag" (the self-contained
    LightRAG strategy) — so methods can be compared live.
    """
    use_lightrag = retrieval == "lightrag"
    use_vector = retrieval not in ("graph", "lightrag")
    use_graph = retrieval not in ("rag", "lightrag")
    # The user's own notes for THIS memory context (the selected save, else the live domain).
    # Read before domain_id is swapped for the save key — beliefs are keyed by the context the
    # user picks, not by the snapshot's internal store name.
    belief_text = await asyncio.to_thread(beliefs.read_beliefs, domain_id, memory, user)
    if memory:
        from app import auth_store
        from app.saves import resolve_stored, save_key

        # The selector shows display names; a user's personal save wins over a
        # shared one of the same name (saves.resolve_stored).
        stored = await asyncio.to_thread(
            resolve_stored, domain_id, memory, auth_store.user_uid(user))
        domain_id = save_key(domain_id, stored)  # retrieve from the snapshot's stores
    query = _last_user(messages)

    yield {"type": "status", "stage": "routing", "detail": "Reading the question in context…"}
    context = _recent_context(messages)
    corpus_map = await _corpus_map(domain_id)
    route_input = f"Recent conversation:\n{context}\n\nLatest message: {query}" if context else query
    if corpus_map:
        route_input = f"Knowledge-base map: {corpus_map}\n\n{route_input}"
    j = await asyncio.to_thread(_judge_sync, _ROUTE_SYS, route_input)
    search_query = (j.get("standalone") or "").strip() or query  # fail open to the raw message
    need = bool(j.get("retrieve", True))  # fail open to grounding
    qtype = j.get("type") if j.get("type") in PROFILES else "factoid"  # fail open to the safe profile

    if context and search_query.strip().lower() != query.strip().lower():
        yield {"type": "status", "stage": "contextualized", "detail": f"Understood as: “{search_query}”"}

    if belief_text:
        yield {"type": "status", "stage": "beliefs", "detail": "Weighing your own notes alongside the answer"}

    if not need:
        yield {"type": "status", "stage": "direct", "detail": "Answering directly — no retrieval needed"}
        convo = messages
        if belief_text and messages:
            convo = list(messages[:-1]) + [_beliefs_msg(belief_text)] + [messages[-1]]
        res = await asyncio.to_thread(lambda: llm_client.chat(
            convo, model=model, reasoning=effort or settings.chat_reasoning))
        for piece in _stream_pieces(res.text or ""):
            yield {"type": "delta", "text": piece}
        yield {"type": "usage", "usage": res.usage.__dict__ if res.usage else None}
        return

    yield {"type": "status", "stage": "route",
           "detail": f"This needs the knowledge base · {qtype} question"}

    final_chunks: list[ScoredChunk] = []
    answer_text, usage, grounded = "", None, True

    stores = {"hybrid": "vector base + graph", "rag": "vector base only",
              "graph": "graph only", "lightrag": "LightRAG memory"}
    for attempt in range(1, max_tries + 1):
        # The retry ladder: attempt 1 runs the router's typed profile; a failed sufficiency
        # check escalates one profile up (factoid → relational → global) AND doubles budgets.
        ptype = _escalate(qtype, attempt - 1)
        prof = PROFILES[ptype]
        detail = (f"Searching the {stores.get(retrieval, 'vector base + graph')}…"
                  if attempt == 1
                  else f"Escalating — retrying as a {ptype} question with a wider net…")
        yield {"type": "status", "stage": "retrieving", "detail": detail}
        chunks, meta = await retrieve(search_query, domain_id=domain_id,
                                      k=prof["k"] * attempt,
                                      graph_limit=prof["graph_limit"],
                                      max_facts=prof["facts"] * attempt,
                                      use_graph=use_graph, use_vector=use_vector,
                                      use_lightrag=use_lightrag)
        final_chunks = chunks
        found = (f"{meta['fused']} sources · LightRAG" if use_lightrag else
                 f"{meta['fused']} sources · {meta['vector']} vector · {meta['graph']} graph")
        yield {"type": "status", "stage": "retrieved", "detail": found}

        if not chunks:
            if attempt < max_tries:
                yield {"type": "status", "stage": "redoing", "detail": "Nothing found — widening the search…"}
                continue
            break

        # Sufficiency (CRAG) gate — only while its verdict can still DO something.
        # On the ladder's last rung "insufficient" can't escalate anything, so the
        # call would re-read every source purely to be ignored: skipped.
        if attempt < max_tries:
            yield {"type": "status", "stage": "grading", "detail": "Checking the sources cover the question…"}
            js = await asyncio.to_thread(_judge_sync, _SUFF_SYS, f"Question: {search_query}\n\nSources:\n{_sources_block(chunks)}")
            if not bool(js.get("enough", True)):
                yield {"type": "status", "stage": "insufficient",
                       "detail": js.get("reason") or "Sources look thin — retrieving more…"}
                continue

        yield {"type": "status", "stage": "answering", "detail": "Composing a grounded answer…"}
        res = await asyncio.to_thread(_generate_sync, messages, chunks, model,
                                      effort, belief_text)
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
