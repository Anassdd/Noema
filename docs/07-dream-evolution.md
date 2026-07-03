# 07 — Dream & the evolutive memory

Dream is Noema's self-maintaining memory: press **✦ Dream** on the graph page and the
memory cleans itself — under strict supervision. This doc covers the concept, the passes,
the safety machinery, configuration, and a scripted demo. Design background:
`studies/NOEMA_EVOLUTION_CONTRACT.md` and `studies/NOEMA_EVOLUTIVE_MEMORY_READABLE.md`.

## Why memories need maintenance

A memory that only accumulates gets *worse*, not just bigger: duplicate entities fragment
knowledge ("BNPP" and "BNP Paribas" each hold half the facts, multi-hop breaks), and
superseded facts keep competing at retrieval time (a dead "the CEO is Alice" is maximally
similar to "who is the CEO?" — it crowds the right answer). Bloat is a **correctness**
problem before it is a storage problem.

The counterweight — and the single most important design input — is a hard research
finding: **letting an LLM freely rewrite its own memory can degrade it below having no
memory at all.** So every mutation in Dream is checkpointed, checked, and reversible.
"Automatic" always means "automatic *and* gated *and* rollback-able".

## What already happens without Dream

Graphiti evolves the graph *at insert time*: entity resolution (dedup against existing
nodes) and contradiction handling (new fact invalidates the old edge, keeping history).
Dream adds the maintenance that **cannot** happen at insert time because it only becomes
visible across many documents.

## The cycle

```
✦ Dream
 ├─ ANALYZE   inspect the graph: duplicate-name candidates? stale superseded
 │            facts past grace? orphan nodes? → build a PLAN (streamed with reasons;
 │            an already-clean memory yields "nothing to improve" and stops)
 └─ for each planned pass:
      checkpoint (GRAPH.COPY) → run pass → CHECK → commit, or ROLL BACK + report
```

One attempt per pass. No retry loops.

### Pass: dedupe — merge split identities

Finds entities whose names suggest the same real thing: identical normalized names,
near-spellings (fuzzy ratio), and **abbreviations** (one name compacting to a prefix of the
other — "bnpp" / "bnp paribas"). Candidate generation is deliberately generous because
every candidate must pass a judge: **one batched LLM call** answers "same real-world
entity?" per pair (so *Apple the company* never merges with *apple the fruit*; fails closed
to "not same"). Confirmed pairs merge: every edge (facts and provenance mentions) repoints
to the survivor with properties intact, and the survivor's summary records the alias
("Also known as: BNPP").

### Pass: forget — demote, don't destroy

Two strict conditions, both required: the fact is **already superseded** (Graphiti
invalidated it at insert — Dream never judges content, so a *current* fact can never be
archived), and it has been dead **longer than the grace window** (`DREAM_GRACE_DAYS`,
default 7 — a fact superseded yesterday is still conversationally alive). Eligible facts
get an `archived` flag: they leave **active retrieval** (`search()` filters them) but stay
in snapshots, the time scrubber, and as-of history. The only true deletion is **orphan
pruning**: entities with zero fact edges — extraction debris, not knowledge.

### Pass: consolidate — currently off by default

Graphiti's `build_communities()` (Leiden clustering + LLM community summaries) is wired but
**disabled**: version 0.29.2 spun at 100 % CPU indefinitely on our FalkorDB setup. Enable
with `DREAM_COMMUNITIES=1` after a library upgrade proves it fixed (there's also a
`DREAM_CONSOLIDATE_TIMEOUT_S` bound). Dedupe + forget are the load-bearing passes either way.

## The safety ritual (the part that makes it trustworthy)

Before each pass the whole graph is checkpointed (`GRAPH.COPY`). After it, the check:

- **episodes unchanged** — the append-only source of truth must survive every pass;
- **no current fact lost** — every pre-pass current edge uuid must still exist;
- **node-loss budget** — the pass may remove *at most* what its own report claims
  (merged + pruned counts); one node more → fail;
- **read consistency** — snapshot edge count must equal the raw Cypher count (a parse
  failure must never masquerade as an empty graph);
- **retrieval probes** — a few real searches over pre-pass facts must still return results.

Any failure → the checkpoint is restored, the pass is reported `rolled_back` with the
reason, and Dream moves on. This is not theoretical: during development the checker caught
a subtle vector-type corruption introduced by the merge pass and rolled it back before any
damage — the gate paying for itself.

Two things are structurally untouchable: **episodes** (raw ingested text) and **history**
(superseded facts remain queryable as-of-time).

## Streaming protocol (what the button actually does)

`POST /graphmem/dream` streams NDJSON; the page narrates and redraws per event:

```
{"phase":"analyze","nodes":128,"edges":342}
{"phase":"plan","passes":[{"key":"dedupe","reason":"0 exact + 1 likely duplicate entities"},…]}
{"phase":"pass_start","pass":"dedupe","reason":"…"}
{"phase":"pass_done","pass":"dedupe","changes":{"merged":1,"details":["BNPP → BNP Paribas"]}, …graph payload…}
{"phase":"pass_rolled_back","pass":"forget","why":"2 current facts lost", …}
{"phase":"done","summary":{"dedupe":{"merged":1},"forget":{"archived":6,"pruned_orphans":0}}}
```

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `DREAM_GRACE_DAYS` | `7` | how long a superseded fact stays in active retrieval before archiving (set `0` for demos) |
| `DREAM_COMMUNITIES` | off | `1` enables the consolidate pass |
| `DREAM_CONSOLIDATE_TIMEOUT_S` | `300` | hard bound on the community build |

## A 3-minute demo that shows every pass

1. Start the backend with `DREAM_GRACE_DAYS=0` (else today's demo facts are "too fresh").
2. On the graph page, paste three texts as separate ingests:
   - `BNP Paribas is a French bank headquartered in Paris. Jean-Laurent Bonnafé leads BNP Paribas.`
   - `BNPP reported strong quarterly earnings. BNPP employs 190,000 people worldwide.`
     *(the alias never co-occurs with the full name — that's what slips past insert-time
     resolution and creates a duplicate node)*
   - `The CEO of Acme Corp is Alice Martin.` — then, as a second ingest:
     `The CEO of Acme Corp is Bob Durand. Alice Martin left Acme Corp.`
3. Observe the dirty state: two nodes for the bank; red "invalidated" count in the stats.
4. *(Optional but wise)* ⧉ Saves → save as `before-dream`.
5. Press **✦ Dream**: watch `BNPP` vanish into `BNP Paribas` live, and the stale CEO fact
   get archived.
6. Verify: click the surviving node (all facts + "Also known as: BNPP"); ask the expert
   chat "who is the CEO of Acme Corp?" (clean Bob answer); drag the time scrubber back
   (the Alice era is still there — demoted, not destroyed).

## Where this is heading (phase 2 proper)

The button is the foundation; the roadmap adds **automatic triggers** (every N episodes /
idle), a **value-scored forgetting** tier (usage + importance + connectivity → demotion,
never deletion), and an **eval gate**: no pass commits unless it beats the pre-pass memory
*and* an episodic-only baseline on a benchmark. See [11 — Roadmap](11-roadmap.md).
