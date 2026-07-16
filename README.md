# Noema

**A domain-expert chatbot whose knowledge is an evolving memory built from your documents.**

You feed Noema PDFs; it builds two synchronized memories from them — a **contextual vector
base** (Anthropic-style Contextual Retrieval: hybrid dense + BM25 over LLM-situated chunks)
and a **temporal knowledge graph** (Graphiti: entities, relationships, and facts that carry
their validity in time). When you chat in expert mode, an agentic pipeline routes, retrieves
from both memories at once, fuses the rankings, grades the evidence, and answers **with
citations back to the exact document and page**. The graph is visible and navigable in 3D,
can be checkpointed and restored ("saves"), carries your own notes alongside the corpus
("beliefs"), and can clean itself on demand ("Dream").

---

## The two surfaces

| Surface | URL | What it does |
|---|---|---|
| **Chat** | `http://localhost:5173/` | Streaming chat with conversations, personas, slash commands, per-chat PDFs, persistent user memory — and **Expert mode**, which grounds answers in the ingested corpus with inline `[S1]` citations and a visible reasoning trace. |
| **Graph Memory** | `http://localhost:5173/?view=graph` | The memory itself: drop PDFs to watch the knowledge graph grow page by page in 3D, travel through time with the scrubber, save/restore named checkpoints, edit your beliefs, and press **✦ Dream** to let the memory self-maintain. |
| **Bench** | `http://localhost:5173/?view=bench` | Compare memory methods on fixed datasets: prepare a corpus, approve gold questions, run closed-book / RAG / graph / hybrid over ONE shared build (never rebuilt, checkpointed as a graph-page save), and read the fixed-schema report. |

### Feature highlights

- **Grounded expert answers** — route → retrieve (vector ⊕ graph, RRF-fused) → grade
  sufficiency (CRAG) → answer → verify faithfulness (Self-RAG), streamed with live status.
- **Query contextualization** — follow-ups like *"what do you know about him?"* are rewritten
  into standalone queries before retrieval, in any language.
- **Temporal graph memory** — facts carry `valid_at` / `invalid_at`; contradictions supersede
  rather than overwrite, so *"who was CEO in 2022?"* still works.
- **✦ Dream** — one-button self-maintenance: merge duplicate entities, archive stale facts,
  every pass checkpointed, sanity-checked, and rolled back if it lost knowledge.
  See [Dream & evolutive memory](docs/07-dream-evolution.md).
- **Saves** — named checkpoints of the *whole* memory (graph + vector base), restore anytime.
- **Beliefs** — your own notes per memory context, kept apart from the corpus; when they
  disagree with the sources the answer presents **both**, attributed.
- **Slash commands** — `/remember`, `/note`, `/character`, `/forget`, `/clear`, `/help`.
- **Provider-portable** — the same code runs on a personal OpenAI key (dev) or a corporate
  OpenAI-compatible endpoint (prod); switching is a `.env` change, never a code change.

---

## Quickstart (macOS dev)

Prerequisites: **Python 3.12** (graphiti-core requirement — one venv holds the vector base
and the graph) and Node 18+.

```bash
# Backend (port 8000)
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your OPENAI_API_KEY in backend/.env
uvicorn app.main:app --reload

# Frontend (port 5173), separate terminal
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, drop a PDF on the Graph page, wait for extraction, switch to
the chat, enable **Expert mode** in Settings, and ask a question about the document.
(With `make` installed: `make backend`, `make frontend`, `make test` wrap the above.)

- **Windows / production:** see [RUN_ON_WINDOWS.md](RUN_ON_WINDOWS.md) (Docker FalkorDB +
  `GRAPH_BACKEND=falkor_server`, llmaas provider, corporate proxy/TLS notes).
- **Every setting explained:** [docs/03-configuration.md](docs/03-configuration.md).

### Taking over this project? The 3-day path

- **Day 1 — run it.** This page top to bottom, then [ARCHITECTURE.md](ARCHITECTURE.md)
  (10 minutes, includes the runtime model), then [GLOSSARY.md](GLOSSARY.md). Do the
  quickstart above; upload one PDF, watch the graph grow, ask one question, click a
  citation. Run `make test` — 9 suites, ~1 min, $0.
- **Day 2 — read it.** [docs/04](docs/04-backend-tour.md)–[07](docs/07-dream-evolution.md)
  with the code side-by-side (the book was written for exactly this); trace one question
  through `backend/app/pipeline.py`. Open [STORAGE.md](STORAGE.md) and find every file
  your Day-1 actions created.
- **Day 3 — trust it.** [studies/README.md](studies/README.md) (the decision record),
  then [docs/12-gotchas.md](docs/12-gotchas.md) (the lessons that were paid for). Run the
  cheap bench end-to-end on `basel-faq` (estimate gate → build → detached run → close the
  tab on purpose → reattach → read the report's confidence intervals).

Operating it day-to-day (runs, saves, keys, failures): [RUNBOOK.md](RUNBOOK.md).

### Switching providers

`LLM_PROVIDER` selects the LLM backend at runtime — no code change:

| Value    | Use                                             | Required vars                                         |
| -------- | ----------------------------------------------- | ----------------------------------------------------- |
| `openai` | local dev (Mac)                                 | `OPENAI_API_KEY` (+ optional model names)             |
| `llmaas` | prod — an Azure-hosted OpenAI-compatible `/v1`  | `LLMAAS_BASE_URL`, `LLMAAS_CHAT_MODEL` (key optional) |

There is no separate `azure` provider — the company endpoint is OpenAI-compatible, so it's
reached through `llmaas`. A second, independent switch — `PARSER` — selects the PDF backend:
`vision` (default, works everywhere) or `docintel` (Azure Document Intelligence).

---

## How it works (one diagram)

```
                 INGESTION (Graph page)                          CHAT (Expert mode)
┌─────────────────────────────────────────────┐   ┌─────────────────────────────────────────┐
│ PDF ──▶ parsing/ (vision LLM per page)      │   │ question ──▶ pipeline.py                │
│   ├──▶ chunking/ ─▶ retrieval/contextual    │   │   1 contextualize + route (one call)    │
│   │      (blurb ▸ embed ▸ Chroma + BM25)    │   │   2 retrieve: vector ⊕ graph, RRF-fuse  │
│   └──▶ graph/ (Graphiti: extract entities,  │   │   3 grade evidence (CRAG)               │
│          resolve, invalidate contradictions)│   │   4 answer w/ citations + your beliefs  │
│                                             │   │   5 verify faithfulness (Self-RAG)      │
│ Same chunks, two lenses, shared provenance  │   │   → streamed: status ▸ text ▸ sources   │
└─────────────────────────────────────────────┘   └─────────────────────────────────────────┘
        every LLM/embedding call goes through app/llm_client.py (the provider seam)
```

---

## Repository map

```
backend/
  app/
    llm_client.py      ← THE provider abstraction (only file importing the OpenAI SDK)
    config.py          ← every env var is read here
    pipeline.py        ← the expert answer loop (route→retrieve→grade→answer→verify)
    parsing/           ← PDF → Markdown (vision default, Azure DI optional)
    chunking/          ← structure-aware Markdown chunker
    retrieval/         ← contextual vector base: Chroma + BM25 + RRF + rerank
    graph/             ← Graphiti temporal graph + Dream evolution + FalkorDB server
    textgraph/         ← dormant instant co-occurrence graph (kept, unused by the UI)
    routers/           ← thin HTTP endpoints
    beliefs.py         ← user notes per memory context
    saves.py           ← whole-memory checkpoints (graph + vector, one key)
frontend/
  src/
    api/               ← one module per backend router (client.js = shared plumbing)
    components/        ← chat surface
    hooks/             ← all state (conversations, stream, commands, memory…)
    graph/             ← the 3D graph page
    lib/               ← system prompt builder, command registry, token counting
tests/                 ← Streamlit lab + scripted test suites (see docs/10-testing.md)
docs/                  ← the book — start at 01
studies/               ← research reports the design decisions come from
```

---

## Documentation

The `docs/` folder is a numbered reading path — a new developer can go top to bottom:

| Doc | What's inside |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The one-pager: layers, the three flows, the single-worker runtime model |
| [STORAGE.md](STORAGE.md) | Every byte of state: where it lives, who writes it, what to back up |
| [RUNBOOK.md](RUNBOOK.md) | Operating it: runs, saves, keys, the top failures and their fixes |
| [GLOSSARY.md](GLOSSARY.md) | The ~30 words this project thinks in |
| [01 — Overview & architecture](docs/01-overview.md) | The concept, the two memories, every flow end-to-end |
| [03 — Configuration](docs/03-configuration.md) | Every env var, typical dev/prod setups |
| [04 — Backend tour](docs/04-backend-tour.md) | Module-by-module walk of `backend/app` |
| [05 — Expert pipeline](docs/05-expert-pipeline.md) | The chat brain: routing, fusion, CRAG/Self-RAG, beliefs |
| [06 — Graph memory](docs/06-graph-memory.md) | Graphiti layer, saves, 3D page, schema induction, gotchas |
| [07 — Dream & evolution](docs/07-dream-evolution.md) | The self-maintaining memory: passes, safety, demo |
| [08 — API reference](docs/08-api-reference.md) | Every endpoint with examples, streaming protocols |
| [09 — Frontend guide](docs/09-frontend.md) | Structure, state model, how to extend |
| [10 — Testing & the lab](docs/10-testing.md) | Streamlit lab, test suites, what's free vs billed |
| [11 — Roadmap & limitations](docs/11-roadmap.md) | What's next (eval bench, more memory types), known limits |
| [12 — Gotchas](docs/12-gotchas.md) | The measured lessons: fusion history, cache economics, fingerprints, judge honesty |
| [Architecture Explorer](docs/architecture.html) | Interactive map of the whole system — open in a browser and click through the layers |

Deep-dives live next to the code they document: [GRAPH.md](backend/app/graph/GRAPH.md),
[RETRIEVAL.md](backend/app/retrieval/RETRIEVAL.md),
[CONTEXTUAL.md](backend/app/retrieval/CONTEXTUAL.md),
[PARSING.md](backend/app/parsing/PARSING.md),
[CHUNKING.md](backend/app/chunking/CHUNKING.md).
Research behind the design: [studies/](studies/).

---

## Project phases

1. **Monofield expert** *(current)* — ingest → dual memory → grounded chat → 3D graph → Dream.
2. **Evolutive memory** — automatic curation triggers, eval-gated; the manual **Dream** button
   is this phase's foundation.
3. **Multifield + routing** — several experts, a router that picks (or declines) the field.

See [the roadmap](docs/11-roadmap.md) for what's deliberately not built yet.
