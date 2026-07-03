# 05 — The expert pipeline

`backend/app/pipeline.py` is the brain of expert mode: everything between a user's message
and a grounded, cited, verified answer. This doc walks the loop stage by stage, explains
each design decision, and lists the exact events the frontend receives.

Expert mode is on when the chat request has `use_memory=true` (the "Expert" toggle in
Settings). Plain chat bypasses all of this.

## The loop at a glance

```
messages ─▶ ① contextualize + route ─▶ (direct answer)              ─▶ done
                     │ retrieve=true
                     ▼
             ② retrieve: vector ⊕ graph → RRF fuse
                     ▼
             ③ grade sufficiency (CRAG)      ── insufficient ──┐
                     ▼                                          │ retry (≤2)
             ④ grounded answer (+ beliefs)                      │
                     ▼                                          │
             ⑤ verify faithfulness (Self-RAG) ── ungrounded ───┘
                     ▼
             stream answer + sources + usage
```

Every stage is announced on the stream as a `status` event — that's the "reasoning trace"
the chat UI renders live.

## ① Contextualize + route — one call, two jobs

**The problem it solves:** the router used to see only the last message. *"Who is Hamlet?"*
retrieved fine; the follow-up *"what do you know about him?"* answered from thin air,
because "him" matches nothing in a search index.

**The fix (conversational-RAG standard):** before anything else, one LLM call receives the
recent turns + the latest message and returns:

```json
{"standalone": "What do you know about Hamlet?", "retrieve": true}
```

- The rewrite resolves pronouns/ellipsis/follow-up references **in the message's own
  language** (no English-specific heuristics — the corpus is partly French).
- Self-contained messages come back unchanged; the first turn skips history entirely.
- The same call decides **whether to retrieve at all** — greetings, small talk, and
  meta-questions answer directly without touching the stores.
- Crucially, the rewrite is used **for search only**; the answer is still generated on the
  real conversation, so tone and context are preserved.

If the message routes to "direct", the user's beliefs (if any) are still injected — then
the answer streams and the pipeline ends there.

## ② Retrieve — two memories, one ranking

`retrieve()` queries both stores and fuses:

- **Vector base:** `retrieval.search_trace()` — dense (embeddings) + BM25 keyword search,
  RRF-fused internally, optional rerank. Runs in a thread (it's sync).
- **Graph:** `GraphMemory.search()` — Graphiti's hybrid fact search. Each returned fact is
  adapted into the same `ScoredChunk` contract (`_fact_to_chunk`), with provenance parsed
  from its episode name (`"report.pdf · p12"` → doc + page), so a graph fact cites exactly
  like a text chunk.
- **Fusion:** the two rankings merge with the shared `rrf()` (imported from `retrieval`) —
  a result found by both lenses rises. Top-k survives.

Why fuse instead of choosing a store per question? A router that picks wrong loses the
answer; fusion degrades gracefully (a wrong lens just adds noise low in the ranking).

## ③ Grade sufficiency (CRAG — check *before* answering)

A cheap LLM judge (`_SUFF_SYS`) looks at the question + fused sources: *do these actually
cover the question?* If not, the pipeline retries retrieval (wider / different) rather than
letting the generator hallucinate around thin evidence. Bounded: max 2 retries, then it
answers with what exists and says what's missing.

## ④ Grounded answer — sources + beliefs, kept apart

The generator receives three separated blocks:

1. **`_GROUND_SYS`** — answer from the numbered sources, cite inline as `[S1]`, prefer
   sources over prior knowledge, answer in the question's language.
2. **`_BELIEFS_SYS` + the user's notes** — the beliefs for this memory context, explicitly
   framed as *the user's personal opinion, not a source*. The rule: when notes and sources
   disagree, present **both**, attributed — "the sources indicate…, while your own note
   holds…" — never silently merge or pick.
3. The conversation itself.

Keeping beliefs epistemically separate from the corpus is deliberate: it is what lets the
expert *disagree with you honestly* instead of being contaminated by your notes.

## ⑤ Verify faithfulness (Self-RAG — check *after* answering)

A second judge (`_FAITH_SYS`) compares the draft against the sources: *is every claim
supported?* An ungrounded draft triggers one more retrieve-and-retry cycle; a grounded one
streams out. Same bounded-retry rule — the loop never spins.

## What the frontend receives (SSE events)

| Event | Payload | Meaning |
|---|---|---|
| `status` | `stage` + human `detail` | the live trace; stages: `routing`, `contextualized`, `beliefs`, `direct`, `route`, `retrieving`, `retrieved`, `redoing`, `grading`, `insufficient`, `answering`, `verifying`, `grounded`/`ungrounded`, `empty` |
| `delta` | `text` | answer tokens as they generate |
| `sources` | list of `{id, doc, pages, text, …}` | the citations behind `[S1]`… |
| `usage` | token counts | for the token-breakdown UI |

Full protocol with example frames: [08 — API reference](08-api-reference.md).

## Memory context: what the expert answers *from*

The request carries `domain` (default `"default"`) and optionally `memory` (a save name).
With a save selected, retrieval hits the save's frozen stores (`saves.save_key()` maps to
the snapshot's graph + collection) — and **beliefs follow the user-facing context** (the
save name), resolved *before* the store swap. So switching memory context switches both the
knowledge and your notes about it, coherently.

## Side quest: `/note` contextualization

`contextualize_note()` (also in `pipeline.py`) cleans a `/note` taken mid-conversation:
resolve references ("he's actually French" → "Hamlet is actually French") and strip filler,
**without altering the claim** — the prompt forbids fact-checking or rewording *even if the
model believes the note is wrong*, because a deliberately-contrarian belief must survive
saving. No chat context → saved verbatim, no LLM call. Fails open to the raw note.

## Costs and knobs

- Per expert answer: 1 route call + 1–2 judge calls + the answer itself (+ retries when
  evidence is thin). Judges run with `temperature=0, max_tokens≈200` — cheap.
- Retry ceiling: 2 (hard-coded in the loop; the "don't loop" rule).
- Retrieval depth, rerank mode: parameters of `retrieve()` / settings.
- Beliefs cap: 8 000 chars per context (`app/beliefs.py`).
