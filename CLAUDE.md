# CLAUDE.md — Build Spec for Noema (Expert Chatbot)

This file is context for Claude Code working in this repo. Read it before generating code.
It describes intent and constraints, not a fixed implementation. Ask before locking in
library choices or schemas that aren't specified here.

## One-line summary

A single-domain (later multi-domain) expert chatbot whose knowledge is an **evolving
GraphRAG memory** built from uploaded documents (mainly research papers), with grounded,
source-citing answers and a **visual, navigable graph**.

## Architecture intent

- **Backend:** Python + FastAPI.
- **Frontend:** React + Vite + Tailwind. Two main surfaces:
  1. an **ingestion page** (upload PDFs / documents → build/extend the graph memory),
  2. a **chat page** (ask questions → grounded answers with references).
  Plus a **graph visualization/navigation view** to inspect the memory.
- **LLM/embedding access MUST be isolated** behind a single provider-abstraction module
  (one client, configured via `.env`). See "Provider abstraction" below — this is the most
  important architectural rule in the project.
- **Memory type is a pluggable, user-selectable strategy.** Classic RAG, LightRAG, and
  GraphRAG are interchangeable implementations behind ONE common interface (ingest, query,
  update, inspect). A setting selects which one answers. Build GraphRAG end-to-end FIRST
  (monitor asked to see it), freeze the interface from it, then add the others — do NOT build
  the abstraction before one method works. Each method keeps its own pre-built store; the
  setting selects which store answers a query, NOT a live rebuild on toggle. Same corpus
  indexed multiple ways enables same-question side-by-side comparison (a deliverable).

## Provider abstraction (critical)

Two target environments share one OpenAI-compatible interface:

- **Dev:** personal Mac, **OpenAI** API key, standard `api.openai.com`.
- **Prod:** locked-down corporate **Windows**, **Azure OpenAI** via an **OpenAI-compatible
  `/v1` endpoint** (different base_url, key, deployment/model names; possible restricted
  package installs).

Rules:
- All chat + embedding calls go through ONE module. The rest of the codebase never imports the
  OpenAI/Azure SDK directly.
- Everything provider-specific (base_url, api_key, model/deployment names, api version) comes
  from `.env` / config. Switching OpenAI ↔ Azure is a config change, NO code change.
- Because Azure here is OpenAI-compatible, prefer using the same SDK with a different base_url
  rather than separate code paths.
- Conditionally include optional params (e.g. token limits) so newer models that reject
  certain keys don't break — don't pass nulls.

## Memory / graph requirements

- Build a knowledge graph (entities + relationships) from documents; keep **provenance**:
  every node/edge should trace back to its source document (and page where possible) so
  answers can cite.
- Support **incremental updates**: adding documents must NOT require rebuilding the whole
  graph.
- Plan for **curation** (update / enhance / clean) in a later phase so the graph stays
  bounded and high-quality — leave seams for this, don't hardcode an append-only design.
- **Extraction quality matters:** entity/relationship extraction should use a capable model,
  even if cheaper models are used elsewhere. A weak extractor produces a sparse, low-value
  graph — flag this rather than silently degrading.
- Expose graph data to the frontend for **visualization and navigation** (nodes, edges,
  source links) and for inspecting retrieval.

## Phasing (don't build ahead of the current phase)

1. **Monofield expert:** ingest → graph memory → grounded chat → graph visualization.
2. **Evolutive memory:** update/enhance/clean rules; keep memory bounded ("don't explode").
3. **Multifield + routing:** multiple experts; route a question to the right field, detect
   multi-field questions, decide if we're actually expert in it. This is an
   orchestration/router layer above the experts.

## Working style

- **CODE STYLE (SUPER IMPORTANT):** Write highly readable, self-explanatory code — clear names,
  small functions, obvious structure. Do NOT add many comments; rely on readable code instead of
  comment noise (keeps token usage low). Comment only where intent is genuinely non-obvious.
- Generate in **staged increments**, smallest working slice first (e.g. bare app → ingest one
  doc → query it → add graph view). Don't generate the whole system at once.
- Keep modules small and single-purpose so pieces can be understood and swapped.
- When a design choice isn't specified here, surface the options and trade-offs instead of
  silently picking one.

## Out of scope / undecided (ask, don't assume)

- Specific GraphRAG library, graph store backend, chunking strategy.
- Phase-2 curation rules and Phase-3 routing strategy.
- Evaluation method for "is it really an expert" — owned by the developer.
