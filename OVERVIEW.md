# Noema — Current State

A snapshot of what is **actually built** today (not the roadmap). Noema's
long-term goal (per `CLAUDE.md`) is a GraphRAG expert chatbot; what exists now is
a polished, provider-agnostic **streaming chat application** with durable
conversations, a persistent user-fact memory, and PDF-to-context — i.e. the
Phase-1 chat shell and the seams where the graph memory will later plug in. The
knowledge graph itself is **not built yet** (see [Not built yet](#not-built-yet)).

---

## Stack

| Layer | Tech |
| --- | --- |
| Backend | Python + FastAPI (app-factory + one router per surface), Pydantic, OpenAI SDK |
| Frontend | React 19 + Vite + Tailwind v4, hooks-based (logic in hooks, components render) |
| Persistence | SQLite (conversations) + JSON file (user facts) — both stdlib, no ORM |
| LLM access | One provider-abstraction module; OpenAI / Azure / any OpenAI-compatible `/v1` |

Two processes run side by side: backend on `:8000`, Vite frontend on `:5173`
(see `README.md` to run them).

---

## Backend

App factory (`app/main.py`) wires CORS for the dev frontend and mounts five
routers. Everything below goes through the provider abstraction — **no other
module imports the OpenAI SDK**.

### Provider abstraction (`llm_client.py`) — the critical seam
- The only file allowed to construct an OpenAI/Azure client.
- `chat(messages, stream=…, model=…, temperature=…, max_tokens=…)` → buffered
  `ChatResult` or a stream of `StreamEvent` (deltas, then one usage event).
- `embed(texts)` and `list_models()` also exposed (embed is **unused so far** —
  ready for RAG).
- Robustness baked in: `max_tokens` is sent **only when set** (newer models
  reject it), and a temperature-related `400` retries without temperature (for
  reasoning models). No per-model table to maintain.

### Configuration (`config.py`) — the only place env vars are read
- `LLM_PROVIDER` ∈ `openai` | `azure` | `llmaas` selects the backend at runtime;
  switching is a `.env` change, **no code change**.
- Resolved once at import into a frozen `Settings` (fail-fast on bad config).
- Knobs: `CHAT_TEMPERATURE` (default `0.2`), `MAX_HISTORY_TURNS` (default `8`).

### Routers (HTTP surface)

| Method + path | Purpose |
| --- | --- |
| `GET /health` | Liveness `{"status":"ok"}` |
| `GET /models` | Chat-capable models at the endpoint + the configured default (non-chat families filtered out) |
| `POST /chat` | **Streamed answer over SSE** — `delta` events, one final `usage`, `error` on failure, `[DONE]` sentinel. History trimmed to `MAX_HISTORY_TURNS` (system messages always kept) |
| `POST /title` | 3–5 word auto-title for a conversation (cheap buffered call) |
| `GET/POST /memory`, `POST /memory/remove`, `DELETE /memory` | CRUD over the user-fact list |
| `POST /memory/auto` | LLM **memory judge**: extract durable user facts from the last exchange |
| `POST /upload` | PDF → extracted text (+ page count); 10 MB cap; rejects non-PDF / encrypted / scanned |
| `GET/DELETE /conversations`, `GET/PUT/PATCH/DELETE /conversations/{id}` | List summaries / clear all / load-save-rename-delete one |

### Stores
- **`conversation_store.py`** — SQLite at `backend/app/conversations.db`. One row
  per conversation; `messages` + `character` + `documents` live in a single JSON
  column (no practical size limit, whole thread loads in one read). Upsert keyed
  on a client-generated id.
- **`memory_store.py`** — user facts in `backend/app/memory.json` (`{"memories":[…]}`).
  These are durable facts about the **user**, distinct from the future document/graph memory.
- **`memory_judge.py`** — the model behind `/memory/auto`. Strict prompt: only
  extract facts the **user explicitly asserted** (never the assistant's guesses),
  always phrased as "The user…"; lenient JSON parsing.
- **`pdf_extract.py`** — `pypdf` text extraction. Per-page text is retained
  (groundwork for future page-level citations). **No OCR** → image-only PDFs are
  rejected with a clear message.

Both stores are gitignored and disposable — delete the file to reset.

---

## Frontend

One chat surface: a collapsible **sidebar** (conversation list) + the **chat
panel** (transcript + composer). Domain logic lives in hooks; components render.

### Hooks (the logic)
- **`useChatStream`** — builds the pinned system message (persona → documents →
  remembered facts), streams the answer into the in-flight assistant message,
  then fires two fire-and-forget extras: auto-title on the first exchange, and
  the memory judge when warranted. Owns streaming/error/abort state.
- **`useConversations`** — lazy: loads sidebar **summaries**, fetches a full
  conversation only when opened. Debounced saves (800 ms), auto-title persistence,
  delete, clear-all. On launch it opens a **fresh empty chat that stays out of
  the sidebar** until the first message.
- **`useSettings`** — feature toggles (memory, auto-capture pre-filter, live
  token estimate), dark mode (session), and **theme family** (persisted).
- **`useCommands`**, **`useMemory`**, **`useModels`**, **`usePdfUpload`**, **`useFileDrop`**.

### Client logic (`lib/`)
- **`commands.js`** — the five slash commands (single source for autocomplete,
  in-input coloring, the command chip, the `/help` card).
- **`systemPrompt.js`** — assembles the system message; documents before memory
  so the cache-friendly prefix stays stable.
- **`memoryFilter.js`** — cheap regex gate that decides whether a turn is worth
  sending to the LLM memory judge (checks both the user message and the reply).
- **`tokens.js`** — real token counts via **lazily-loaded tiktoken** (`o200k_base`,
  ~2 MB in its own chunk), with a 4-chars/token fallback until it lands.

### Slash commands
`/remember <fact>` · `/character <persona>` · `/forget <text>` · `/clear` · `/help`
— all handled client-side, no model call. `/forget` opens a confirm dialog on
multiple matches.

### UX features
- SSE streaming with **paced word-reveal**, typing dots, and a blinking caret.
- **Per-message token accounting** (context + prompt + response) and a
  session-wide token meter; optional live token estimate while typing.
- Auto-scroll (instant while streaming), jump-to-bottom, copy buttons.
- PDF attach via composer button, **drag-and-drop**, or the Documents panel.
- Memory "Remembered: …" notes, the `/help` card, and themed notifications.

### Theming
- All colors/fonts are **CSS variables** → two theme families, each with
  light + dark:
  - **Aurora** — Newsreader serif wordmark/headings, Inter body, gradient
    wallpaper + frosted glass panel.
  - **Codex** — Geist grotesque throughout, flat solid surfaces (no gradient,
    no blur), bolder type.
- Chosen in **Settings → Theme** (staged + Confirm button, with live previews);
  the family persists across reloads, dark mode is per session.

---

## Where things live (data flow)

| Thing | Stored as | Scope |
| --- | --- | --- |
| Conversations (messages, persona, attached docs) | SQLite `conversations.db` | Durable, all sessions |
| User facts (`/remember` + auto-judge) | `memory.json` | Durable, all chats |
| Persona (`/character`) | Inside the conversation row | Per conversation |
| Attached PDFs | Extracted text inside the conversation row, **stuffed into the system prompt** | Per conversation |
| Theme family | `localStorage` | Per browser |
| Dark mode / feature toggles | React state | Per session |

---

## Not built yet

These are the headline Noema goals from `CLAUDE.md` that **do not exist** in the
code today — useful to know before extending:

- **The knowledge graph itself.** No entity/relationship extraction, no graph
  store, no provenance, no graph visualization/navigation view.
- **RAG / retrieval.** PDFs are passed as **full text in the system prompt**, not
  chunked, embedded, or retrieved. `embed()` exists but is unused; no vector store.
- **Pluggable memory strategies** (Classic RAG / LightRAG / GraphRAG behind one
  interface) — current "memory" is the simple user-fact list only.
- **Phase 2** (incremental updates, curation/cleaning to keep the graph bounded)
  and **Phase 3** (multi-field experts + routing).
- **A dedicated ingestion page** — ingestion today is just PDF attach in the chat.

The seams are in place for these: `documents.py` is where ingestion lands,
`embed()` is ready, per-page PDF text is retained for citations, and the provider
abstraction means none of it needs new LLM plumbing.
