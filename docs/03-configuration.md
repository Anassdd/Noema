# Configuration reference

This page lists every environment variable the system reads, what it does, its default, and
which provider or mode it applies to. All backend configuration lives in `backend/.env`
(loaded by path in `backend/app/config.py` and `backend/app/graph/config.py`, so it works
regardless of the working directory — uvicorn runs from `backend/`, the test lab from the
repo root). Settings are resolved **once at import** and fail fast: a missing required
variable raises `ConfigError` at startup, not on the first request. Frontend variables live
in `frontend/.env` and use Vite's `VITE_` prefix. Endpoints that consume these settings are
documented in the [HTTP API reference](08-api-reference.md).

## Provider

Read in `backend/app/config.py` (`load_settings`). `LLM_PROVIDER` selects one of two
OpenAI-compatible backends; everything else in the codebase goes through the single
provider-abstraction module (`app/llm_client.py`) and never touches an SDK directly.
Switching providers is a config change only.

| Variable | Default | Applies to | What it does |
|---|---|---|---|
| `LLM_PROVIDER` | `openai` | all | Selects the provider: `openai` (dev Mac, personal key, standard endpoint) or `llmaas` (any OpenAI-compatible `/v1` endpoint at a custom URL, e.g. the corporate Azure-hosted gateway). |
| `OPENAI_API_KEY` | — **required** | `openai` | Personal OpenAI API key. |
| `LLMAAS_BASE_URL` | — **required** | `llmaas` | Base URL of the OpenAI-compatible endpoint, e.g. `https://<host>/v1`. |
| `LLMAAS_API_KEY` | `""` (optional) | `llmaas` | Key for the gateway. May stay blank for a keyless gateway — `llm_client` supplies a placeholder the SDK requires but the server ignores. |

## Models

Also read in `backend/app/config.py`. Model names are whatever the chosen endpoint expects —
the rest of the app just passes them through.

| Variable | Default | Applies to | What it does |
|---|---|---|---|
| `OPENAI_CHAT_MODEL` | `gpt-4.1-mini` | `openai` | Chat/judge/answer model (routing, grading, grounded answers). |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-large` | `openai` | Embedding model for the RAG vector base. Dimension is read dynamically downstream, so swapping is safe. Chosen for multilingual retrieval (French corpus). |
| `OPENAI_PARSE_MODEL` | `gpt-4o` | `openai` | Vision model used to parse PDF pages (render → image → Markdown + LaTeX). Must be vision-capable. |
| `LLMAAS_CHAT_MODEL` | — **required** | `llmaas` | Chat model name exactly as the endpoint exposes it. |
| `LLMAAS_EMBED_MODEL` | `""` | `llmaas` | Embedding model on the endpoint. **Required in practice for RAG retrieval** — without it the vector base cannot index or search (the graph path still works). |
| `LLMAAS_PARSE_MODEL` | falls back to `LLMAAS_CHAT_MODEL` | `llmaas` | Vision-capable deployment for PDF parsing. |
| `CHAT_TEMPERATURE` | `0.2` | both | Default generation temperature (overridable per call in `llm_client.chat()`). |
| `MAX_HISTORY_TURNS` | `8` | both | Cap on user/assistant turns kept in chat history (one turn = user + assistant; system messages always stay). Consumed by the `/chat` route. |

## Parser

The parser backend is orthogonal to the LLM provider — read in `backend/app/config.py`
(`_common`), shared by both providers.

| Variable | Default | What it does |
|---|---|---|
| `PARSER` | `vision` | `vision` = render pages locally and transcribe with the vision model (works anywhere the LLM does); `docintel` = Azure Document Intelligence (deterministic, in-tenant, page provenance). |
| `DOCINTEL_ENDPOINT` | `""` | Azure Document Intelligence endpoint, e.g. `https://<resource>.cognitiveservices.azure.com/`. Required only when `PARSER=docintel`. |
| `DOCINTEL_KEY` | `""` | Azure Document Intelligence key. Required only when `PARSER=docintel`. |

## Retrieval / Reranker

Read in `backend/app/config.py` (`_common`).

| Variable | Default | What it does |
|---|---|---|
| `VECTOR_DIR` | `""` → `backend/.chroma` | Where the embedded Chroma vector store persists (`app/retrieval/store.py`). |
| `RERANK_MODEL` | `""` | Optional dedicated reranker (no-GPU seam). Empty = no dedicated reranker; the engine can still fall back to LLM-based reranking. |
| `RERANK_BASE_URL` | `""` | Base URL of the reranker endpoint. |
| `RERANK_API_KEY` | `""` | Key for the reranker endpoint. |

## Graph

Read in `backend/app/graph/config.py` (`load_graph_config`). The graph store backend is
swappable without touching graph logic. LLM/embedder credentials are deliberately **not**
duplicated here — they come from the provider settings above.

| Variable | Default | What it does |
|---|---|---|
| `GRAPH_BACKEND` | `falkor_local` | One of: `falkor_local` — auto-runs the FalkorDB server bundled inside `falkordblite` as one shared local process (no Docker, no install; **Unix-only**); `falkor_embedded` — pure in-process redislite, lightest but flaky under Graphiti's concurrent writes; `falkor_server` — an external FalkorDB server (use on Windows, see [Typical setups](#typical-setups)); `neo4j` — a Neo4j server. |
| `GRAPH_DB_DIR` | `<repo>/tests/results/graph_store` | Where the `.rdb` persistence lives for the local/embedded backends. |
| `FALKOR_HOST` | `127.0.0.1` | Host for `falkor_local` / `falkor_server`. |
| `FALKOR_PORT` | `6399` | Port for `falkor_local` / `falkor_server`. Defaults to 6399 to avoid clashing with a system redis on 6379; a Docker FalkorDB usually publishes 6379. |
| `FALKOR_USER` | `""` | Username, if the graph server requires auth. Also used as the Neo4j username. |
| `FALKOR_PASSWORD` | `""` | Password, if the graph server requires auth. Also used as the Neo4j password. |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI (`GRAPH_BACKEND=neo4j` only). |
| `GRAPH_EXTRACT_MODEL` | `""` | Model used for entity/relationship extraction. Blank = resolved from the provider settings. Extraction quality matters — a weak extractor produces a sparse graph. |

## Dream (graph self-maintenance)

Read in `backend/app/graph/evolution.py`. Dream is the streamed self-maintenance cycle
(dedupe → forget → consolidate) triggered by `POST /graphmem/dream`.

| Variable | Default | What it does |
|---|---|---|
| `DREAM_GRACE_DAYS` | `7` | Grace period before the *forget* pass archives superseded/invalidated facts out of active retrieval. Facts younger than this stay visible. |
| `DREAM_COMMUNITIES` | unset (off) | Set to `1` to enable the *consolidate* pass (Graphiti's `build_communities`). Off by default: graphiti 0.29.2's community build spun at 100% CPU indefinitely on the project's FalkorDB setup — re-test on library upgrades before enabling. |
| `DREAM_CONSOLIDATE_TIMEOUT_S` | `300` | Timeout for one community build. A hung build fails the pass (which rolls back) instead of wedging Dream. |

## Beliefs

Read in `backend/app/config.py` (`_common`), consumed by `backend/app/beliefs.py`.

| Variable | Default | What it does |
|---|---|---|
| `BELIEFS_DIR` | `""` → `backend/.beliefs` | Where the per-(user, memory-context) note files persist. Small markdown files (max 8000 chars each), injected verbatim into answer prompts — never indexed into RAG or the graph. |

## Frontend

Read via `import.meta.env` — set them in `frontend/.env` (Vite loads it automatically).

| Variable | Default | Read in | What it does |
|---|---|---|---|
| `VITE_API_BASE` | `http://localhost:8000` | `frontend/src/api/client.js` | Backend base URL for every API call. Set it when the backend runs on another host/port. |
| `VITE_DOC_STUFF_MAX_TOKENS` | `150000` | `frontend/src/lib/systemPrompt.js` | Token budget for chat-attached PDFs stuffed directly into the system prompt (budget is on the **total** of all attached documents). Above the budget, the chat tells the user to index the documents on the Graph Memory page instead. Set `0` to disable stuffing entirely. Lower it if the deployed model has a small context window. |

Note: CORS is not configurable by env — `backend/app/main.py` hardcodes
`http://localhost:5173` (the Vite dev server) as the allowed origin.

## Typical setups

Copy `backend/.env.example` to `backend/.env` and fill in. Never commit the real `.env`
(`.gitignore` already excludes it). The values below are shapes, not real keys.

### (a) macOS dev — OpenAI

The bundled FalkorDB (`falkor_local`, the default) works on macOS, so no graph
configuration is needed at all. The model defaults apply.

```dotenv
# backend/.env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# Optional — these are the code defaults if unset:
# OPENAI_CHAT_MODEL=gpt-4.1-mini
# OPENAI_EMBED_MODEL=text-embedding-3-large
# OPENAI_PARSE_MODEL=gpt-4o

# Optional knobs:
# PARSER=vision
# CHAT_TEMPERATURE=0.2
# MAX_HISTORY_TURNS=8
# GRAPH_BACKEND=falkor_local        # the default; no server or Docker needed on macOS
```

### (b) Windows prod — llmaas + Docker FalkorDB

The bundled FalkorDB is Unix-only, so on Windows the graph runs as a server (Docker) and
the app points at it — see `RUN_ON_WINDOWS.md` for the full walkthrough. Start the server
first:

```powershell
docker run -d --name falkordb -p 6379:6379 -v falkordb_data:/data falkordb/falkordb:latest
```

```dotenv
# backend/.env
LLM_PROVIDER=llmaas
LLMAAS_BASE_URL=https://<your-endpoint-host>/v1
LLMAAS_API_KEY=                       # leave blank for a keyless gateway

# Model / deployment names EXACTLY as your endpoint exposes them:
LLMAAS_CHAT_MODEL=<a capable, not-too-expensive chat model>
LLMAAS_EMBED_MODEL=<an embedding model>       # REQUIRED for RAG retrieval
LLMAAS_PARSE_MODEL=<a vision-capable model>   # falls back to LLMAAS_CHAT_MODEL

# Graph store: a server, because the bundled one is Unix-only
GRAPH_BACKEND=falkor_server
FALKOR_HOST=127.0.0.1
FALKOR_PORT=6379
# FALKOR_USER=                        # only if your FalkorDB requires auth
# FALKOR_PASSWORD=

# Optional:
# PARSER=vision                       # or docintel (+ DOCINTEL_ENDPOINT / DOCINTEL_KEY)
# VECTOR_DIR=                         # default: backend\.chroma
# CHAT_TEMPERATURE=0.2
```

If Docker is not allowed but Neo4j is, swap the graph block for:

```dotenv
GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7687
FALKOR_USER=neo4j
FALKOR_PASSWORD=<password>
```

Run the backend with a **single worker** (`uvicorn app.main:app --reload`) — the FalkorDB
driver binds to one event loop, so `--workers N` breaks it.
