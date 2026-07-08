# Running Noema on Windows (corporate OpenAI-compatible endpoint)

This guide gets Noema running on a locked-down **Windows** work PC against your
**OpenAI-compatible `/v1` endpoint** (the `llmaas` provider). It also records exactly
which parts are Windows-native and which need a small change.

---

## TL;DR — does it work on Windows?

**Yes, with one change to the graph store.** Everything talks to your endpoint through one
provider abstraction (the OpenAI SDK with a custom `base_url`), and every other dependency
has Windows wheels. The **only** blocker is the *bundled* FalkorDB: it ships inside
`redislite`, which is **Unix-only**. On Windows you run FalkorDB as a **server** (Docker)
and point the app at it — a one-line `.env` change, no code change.

| Component | Windows? | Notes |
|---|---|---|
| Chat + retrieval pipeline (router → CRAG → answer → Self-RAG) | ✅ | Pure Python + your endpoint |
| LLM / embeddings (`llmaas`) | ✅ | OpenAI SDK + `base_url`; no Azure SDK, no code path change |
| RAG vector store (Chroma) | ✅ | Windows wheels on `chromadb>=1.0` |
| BM25 keyword search | ✅ | Pure Python |
| PDF parsing (vision) | ✅ | `pypdfium2` has Windows wheels; parsing runs on your endpoint |
| Azure Document Intelligence parser (optional) | ✅ | Pure-Python HTTP client |
| **Graph memory (Graphiti + FalkorDB)** | ⚠️ | Bundled `falkordblite`/`redislite` is **Unix-only** → run FalkorDB in **Docker** and set `GRAPH_BACKEND=falkor_server` (or use Neo4j) |
| Frontend (React + Vite) | ✅ | Node.js, cross-platform |

> If you only need the **chat + RAG expert** (no 3D graph page), you can even skip Docker —
> set `GRAPH_BACKEND=falkor_server` but simply don't open the graph page. Retrieval fuses
> whatever graph is reachable; with no graph server it falls back to the vector base alone.
> For the full product (graph page + graph-fused answers), run the FalkorDB container below.

---

## 1. Prerequisites

- **Python 3.12** (not 3.13/3.14 — Graphiti's dependency tree targets 3.12). Install from
  python.org; tick *"Add Python to PATH"*.
- **Node.js 18+** (nodejs.org).
- **Docker Desktop** (docker.com) — only for the FalkorDB graph server.
- **Git**.

Check:
```powershell
python --version   # 3.12.x
node --version     # 18+
docker --version
```

---

## 2. Get the code
```powershell
git clone <your-repo-url> Noema
cd Noema
```

---

## 3. Backend

### 3a. Virtual env + dependencies (Windows-safe set)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-windows.txt
```
`requirements-windows.txt` is the normal set **minus** the Unix-only `graphiti-core[falkordblite]`,
**plus** the pure-Python `falkordb` client that connects to a FalkorDB server.

> If `chromadb` fails to build, install the **"Microsoft C++ Build Tools"** (Desktop
> development with C++) once, then re-run the `pip install`. Recent `chromadb` wheels
> usually avoid this.

### 3b. Start FalkorDB (the graph server)
```powershell
docker run -d --name falkordb -p 6379:6379 -v falkordb_data:/data falkordb/falkordb:latest
```
This persists to a Docker volume and survives restarts. To stop/start later:
`docker stop falkordb` / `docker start falkordb`.

### 3c. Configure `backend\.env`
Create `backend\.env` (copy from `.env.example` if present). For the **corporate endpoint**:
```dotenv
# --- Provider: your OpenAI-compatible /v1 endpoint ---
LLM_PROVIDER=llmaas
LLMAAS_BASE_URL=https://<your-endpoint-host>/v1
LLMAAS_API_KEY=<key, or leave blank for a keyless gateway>

# Model / deployment names EXACTLY as your endpoint exposes them:
LLMAAS_CHAT_MODEL=<a capable, not-too-expensive chat model>
LLMAAS_EMBED_MODEL=<an embedding model>          # REQUIRED for RAG retrieval
LLMAAS_PARSE_MODEL=<a vision-capable model>       # for PDF parsing (falls back to chat model)

# --- Graph store: a server, because the bundled one is Unix-only ---
GRAPH_BACKEND=falkor_server
FALKOR_HOST=127.0.0.1
FALKOR_PORT=6379
# FALKOR_USER=            # only if your FalkorDB requires auth
# FALKOR_PASSWORD=

# --- Optional ---
# PARSER=vision            # or docintel (+ DOCINTEL_ENDPOINT / DOCINTEL_KEY)
# VECTOR_DIR=              # where Chroma persists (default: backend\.chroma)
# CHAT_TEMPERATURE=0.2
```

> **Important about the endpoint:** RAG needs an **embeddings** model on your endpoint
> (`LLMAAS_EMBED_MODEL`). If your gateway only exposes chat models, retrieval from the
> vector base won't work — the graph path still will. Confirm an embeddings deployment
> exists before relying on RAG.

> Running dev-style on Windows with your **personal OpenAI** key instead? Use
> `LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`, and the new defaults apply
> (`gpt-5.4-mini`, `text-embedding-3-large`) — still keep `GRAPH_BACKEND=falkor_server`.

### 3d. Run the backend (single worker)
```powershell
.venv\Scripts\activate
uvicorn app.main:app --reload
```
Keep it to **one worker** (`--reload` already is). The FalkorDB driver binds to one event
loop — don't pass `--workers N`.

Backend is on **http://localhost:8000**.

---

## 4. Frontend
Open a **second** terminal:
```powershell
cd Noema\frontend
npm install
npm run dev
```
- Chat: **http://localhost:5173**
- Graph page: **http://localhost:5173/?view=graph**

> The frontend calls `http://localhost:8000` by default. If the backend runs elsewhere,
> set `VITE_API_BASE` (e.g. create `frontend\.env` with `VITE_API_BASE=http://host:8000`).

---

## 5. First run checklist
1. Docker FalkorDB container is **up** (`docker ps`).
2. `backend\.env` has `LLM_PROVIDER=llmaas`, a valid `LLMAAS_BASE_URL`, and the three model
   names your endpoint exposes.
3. Backend started with no config error (it fails fast on missing vars).
4. Open the **graph page**, drop a PDF → watch the graph build **and** the RAG base index
   (the status line shows `Indexing … into the search base`).
5. Open the **chat**, ask a question about that PDF → you should see the runtime trace and
   cited sources.

---

## 6. Alternative: Neo4j instead of FalkorDB
If Docker/FalkorDB isn't allowed but Neo4j is, the graph driver supports it:
```dotenv
GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7687
FALKOR_USER=neo4j
FALKOR_PASSWORD=<password>
```
(Run Neo4j via Docker `docker run -p 7687:7687 -e NEO4J_AUTH=neo4j/<pw> neo4j:5`, or Neo4j
Desktop.) No code changes — it's a `.env` switch.

---

## 7. Troubleshooting
- **`redislite` / `falkordblite` install error** → you used `requirements.txt`. Use
  `requirements-windows.txt` (it drops the Unix-only bundle).
- **Graph page empty / graph errors** → FalkorDB container isn't running or `FALKOR_PORT`
  doesn't match the container's published port.
- **RAG returns nothing** → `LLMAAS_EMBED_MODEL` unset or the endpoint has no embeddings
  model; or you haven't (re-)uploaded PDFs since enabling RAG.
- **`ConfigError: Missing required environment variable`** → a required `.env` var is blank
  (for `llmaas`: `LLMAAS_BASE_URL`, `LLMAAS_CHAT_MODEL`).
- **Port already in use (8000/5173/6379)** → stop the other process or change the port.
