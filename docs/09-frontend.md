# Frontend guide

The frontend is a React 19 + Vite + Tailwind app in `frontend/src/`. It has no router
library, no global state store, and no component framework: two views selected by a
query param, hooks that own all state, a small hand-written `api/` layer, and plain
components. This page maps the whole tree and ends with recipes for the three most
common changes.

Backend endpoints referenced here are documented in the [API reference](08-api-reference.md);
the server side of each call is in the [backend tour](04-backend-tour.md).

## How the app mounts — two views

`index.html` → `main.jsx`:

```jsx
const GraphMemoryPage = lazy(() => import("./graph/GraphMemoryPage.jsx"));
const view = new URLSearchParams(window.location.search).get("view");
// view === "graph" ? <GraphMemoryPage /> : <App />
```

- **Default** (`/`) — the chat surface, `App.jsx`.
- **`/?view=graph`** — the graph-memory page, opened in a separate tab by the header's
  graph button. It pulls in three.js, so it is **lazy-loaded**: the chat bundle never
  pays for it.

`App.jsx` composes the chat surface: it instantiates the top-level hooks
(`useConversations`, `useMemory`, `useModels`, `useSettings`), holds a few bits of pure
UI state (which panels are open, session token total, the selected memory snapshot),
and passes everything down as props.

## State model — hooks own everything

There is no Redux/Zustand/context store. Each concern is one hook; components are
mostly presentational. Data flows down as props, mutations flow up as callbacks.

| Hook | Owns | Notes |
| --- | --- | --- |
| `hooks/useConversations.js` | The sidebar summaries + the one fully-loaded active conversation (messages, persona, attached PDFs). | Saves edits back with an **800 ms debounce** (`scheduleSave`/`flushSave`); never persists a brand-new untouched chat (`isPersistable`); `skipSave` suppresses the save that merely loads/switches a conversation in; `autoTitle()` names a chat from its first exchange and persists by id even if you've switched away. |
| `hooks/useChatStream.js` | One chat turn: streaming/error/abort state. | Builds the request (system prompt via `buildSystemMessage` + real user/assistant turns only — `note`/`help` rows are stripped), streams deltas into the in-flight assistant message, attaches `usage`/`trace`/`sources` onto that message, then fires the fire-and-forget extras: auto-title on the first exchange, and the memory judge (gated by the prefilter regexes when enabled). |
| `hooks/useCommands.js` | Slash-command dispatch + the `/forget` confirmation state. | `runCommand(text)` returns `true` if the text was a command (handled locally), `false` to fall through to a chat request. |
| `hooks/useMemory.js` | The cross-conversation user facts. | Every API call returns the full list, which is taken as the source of truth. `judgeMemory(recent)` returns the newly-added facts so the chat can confirm them inline. |
| `hooks/useSettings.js` | Feature switches (memory, expert mode, prefilter, tokenizer) + appearance (dark mode, theme family). | Theme family persists in `localStorage`; dark mode is a `dark` class on `<html>`, theme a `data-theme` attribute. Feature switches are session-only (reset on reload). |
| `hooks/usePdfUpload.js` | Uploading/attaching a PDF to the active conversation. | Calls `POST /upload`, appends `{id, filename, pages, chars, text}` to the conversation's documents. |
| `hooks/useFileDrop.js` | Whole-area drag-and-drop. | Depth counter so child elements don't flicker the overlay; reacts only to file drags. |
| `hooks/useModels.js` | Available chat models + the current selection. | Re-fetchable (`loadModels`) because a one-shot load can fail silently during a backend restart; always keeps the default selectable. |

## `api/` — one module per backend router

`api/client.js` is the single place the backend address and shared response plumbing
live:

- `API_BASE` — `VITE_API_BASE` or `http://localhost:8000`.
- `asJson(res)` — resolve to JSON, surfacing the backend's human `detail` on errors.
- `readNdjsonStream(res, onEvent)` — consume an NDJSON streaming response line by
  line (used by graph ingestion and Dream).

| Module | Backend router | What it wraps |
| --- | --- | --- |
| `api/chat.js` | `chat.py` | `streamChat(messages, handlers)` — POSTs to `/chat` and hand-parses the SSE frames off the `ReadableStream` (native `EventSource` is GET-only, so it can't send a JSON body). Dispatches `delta` / `usage` / `status` / `sources` events to handlers; throws on an `error` event. |
| `api/title.js` | `chat.py` | `fetchTitle(messages)` → `POST /title`. |
| `api/conversations.js` | `conversations.py` | list / get / save (PUT upsert) / rename / delete / clear. |
| `api/memory.js` | `memory.py` | fetch / save / remove / clear facts + `autoMemory(messages)` (the LLM judge). |
| `api/upload.js` | `documents.py` | `uploadPdf(file)` → `POST /upload`, returns the parsed text. |
| `api/graphmem.js` | `graphmem.py` | `getGraph`, `ingestText`, `resetGraph`, the saves (`listSaves`/`saveGraph`/`restoreGraph`/`deleteSave`), and the two NDJSON streams: `uploadPdfStream` (a fresh graph snapshot per extracted page) and `dreamStream` (self-maintenance passes). |
| `api/beliefs.js` | `beliefs.py` | `getBeliefs` / `saveBeliefs` per memory context + `addBelief` (the `/note` command; sends recent turns so the backend can resolve references). |
| `api/models.js` | `system.py` | `fetchModels()` → `/models`. |

## `lib/` — pure logic, no React

| File | One-liner |
| --- | --- |
| `lib/systemPrompt.js` | `buildSystemMessage(character, memories, documents)` — the single system message pinned in front of every chat request: persona → attached PDFs → remembered facts (documents before memory so the cacheable prefix stays stable). PDFs are **stuffed whole** into the prompt while the total stays under `DOC_STUFF_MAX_TOKENS` (default 150 000, env `VITE_DOC_STUFF_MAX_TOKENS`, budget on the *total* of all attached docs); over budget, the model is told it cannot see them and to send the user to the Graph Memory page for indexed retrieval. |
| `lib/commands.js` | The `COMMANDS` registry — the single source of truth for the autocomplete menu, the in-input coloring, the command chip, and the `/help` card. Plus `findCommand(text)` (exact leading `/word` match) and `matchCommands(text)` (partial-command autocomplete). |
| `lib/memoryFilter.js` | The cheap client-side gate in front of the LLM memory judge: `looksMemorable(userText)` and `replyLooksMemorable(answer)` regex heuristics. Intentionally permissive — the judge is the real filter; this only skips obviously non-personal turns to save a model call. |
| `lib/tokens.js` | `estimateTokens(text)` — real tiktoken `o200k_base` counting, lazily loaded in its own chunk (~2 MB of tables); falls back to the ~4-chars-per-token heuristic until it lands. |

## `components/` — the chat surface tree

```
App
├── Sidebar                      conversation list, new chat, clear history, settings
├── (header)  ModelSelector      searchable model dropdown
├── ChatWindow                   one conversation: transcript + composer; wires the hooks
│   ├── MessageList              transcript; auto-scrolls only when already near the bottom
│   │   └── Row                  user bubble / assistant answer / "note" pill / "help" card
│   │       ├── Markdown (lazy)  parser + highlighter in their own chunk
│   │       ├── PacedAnswer      word-by-word reveal while streaming
│   │       ├── TracePanel       the expert pipeline's live status steps (routing → … → grounded)
│   │       └── Sources          collapsible cited sources, tagged graph / vector
│   ├── MessageInput             auto-growing composer: command autocomplete + coloring,
│   │   └── MemorySelector       PDF attach, token/model footer; picks Live memory vs a saved
│   │                            snapshot (shown only in expert mode)
│   ├── EmptyState               first-run greeting
│   ├── DocumentsPanel           drawer: the conversation's attached PDFs
│   └── ForgetDialog             multi-match /forget picker (keyboard-driven)
├── MemoryPanel                  drawer: saved facts, remove one / clear all
├── SettingsModal                theme cards + feature toggles (Toggle) + clear-memory
└── ConfirmDialog                reusable destructive-action confirm
```

Support files: `icons.jsx` (inline stroke icons, `currentColor`), `Toggle.jsx`,
`ConfirmDialog.jsx`. Message roles beyond `user`/`assistant`: `note` (confirmation
pill, e.g. "Saved to memory…") and `help` (the command card) — both rendered locally
and **filtered out of what is sent to the model**.

## `graph/` — the 3D memory page

| File | One-liner |
| --- | --- |
| `graph/GraphMemoryPage.jsx` | The whole `?view=graph` surface (~1 500 lines, state + rendering in one place). A `3d-force-graph` scene showing Graphiti's entities and temporal facts: node size by degree, color by community, custom sprite/mesh nodes with a facing-the-camera depth cue, focus mode on hover/click, an inspector panel, and a **time slider** that scrubs the memory "as of" a date (built from each fact's `created_at`). Two view modes: **concepts** (every entity) and **topics** (one cube per Louvain community, via `topicsFrom`). Ingestion: drop a PDF → `uploadPdfStream` NDJSON events redraw the graph after each extracted page (node objects are reused so positions persist and new nodes fly in from a connected parent); paste text → `ingestText`. Also drives Dream (`dreamStream`, narrated passes), reset, and the two toolbar panels below. |
| `graph/graph3d.js` | Graph enrichment: `enrich(nodes, links)` runs **Louvain community detection** (graphology) and mutates nodes in place — `community` → color from `PALETTE`, degree → `val` (size) — so 3d-force-graph keeps positions across updates. `topicsFrom(nodes, links)` collapses the graph to one topic node per community with aggregated cross-cluster edges. |
| `graph/panels.jsx` | Pure presenters for the toolbar popovers: `SavesPanel` (name + save the current memory, list/restore/delete checkpoints) and `BeliefsPanel` (the user's own notes per memory context — live memory or a save). All state and handlers live in `GraphMemoryPage`. |
| `graph/styles.js` | Shared inline styles for the page (dark glassy language): buttons, panels, toolbar, time bar, spinner. |

Saves made here are what the chat composer's `MemorySelector` offers as "answering
from" contexts — a save checkpoints the graph **and** the RAG store together (see
`saves.py` in the [backend tour](04-backend-tour.md)).

## Slash commands

Typed into the composer; `ChatWindow.send()` tries `runCommand(text)` first and only
falls through to a chat request if it isn't a command. The registry in
`lib/commands.js` drives autocomplete (`/` + ↑↓ + Enter/Tab), in-input coloring, and
the `/help` card; the behavior lives in `hooks/useCommands.js`.

| Command | What it does | Client side | Server side |
| --- | --- | --- | --- |
| `/remember <fact>` | Save a durable user fact across all chats. | Checks `memoryEnabled`, calls `useMemory.addMemory`, adds a confirmation pill. | `POST /memory` → appended to `memory.md`. The fact rides along in every future system prompt. |
| `/note <text>` | Add a note to the **current memory context's** beliefs (the save selected in the composer, else live memory). | Sends the note + the last 8 real turns, shows a pill with what was actually saved. | `POST /beliefs/add` → resolves references ("he", "that") against the turns without altering the claim, appends to the context's beliefs file. The expert weighs it against the sources. |
| `/character <desc>` | Set the conversation's persona (empty clears it). | Entirely client-side: stored on the active conversation, injected by `buildSystemMessage`. | None directly — persisted only as part of the conversation upsert. |
| `/forget <text>` | Remove saved fact(s) by substring. | Matches against fact content (the "The user…" prefix is stripped first, so `/forget user` doesn't match everything). One match → removed; several → `ForgetDialog`. | `POST /memory/remove` per removed fact. |
| `/clear` | Wipe this conversation's transcript. | Client-only: `setMessages([])`. Memory and attached PDFs stay. | None. |
| `/help` | Show the command guide card. | Client-only: appends a `help` row (never sent to the model). | None. |

## Recipes

### Add a new API call

1. If it belongs to an existing backend router, add a function to the matching
   `frontend/src/api/<module>.js`; a new router gets a new module. Always import from
   `client.js`:

   ```js
   // api/graphmem.js
   import { API_BASE, asJson } from "./client.js";

   export function exportGraph(domain = "default") {
     return fetch(`${API_BASE}/graphmem/export?domain=${domain}`).then(asJson);
   }
   ```

2. Consume it from a hook (stateful) or directly in the component that triggers it
   (one-shot, like the graph page's handlers).
3. Backend side: add the endpoint to the router in `backend/app/routers/` — and if it
   is a whole new router, include it in `create_app()` in `backend/app/main.py`.
   Document it in the [API reference](08-api-reference.md).

### Add a new slash command

1. Register it in `frontend/src/lib/commands.js` — this alone makes it appear in the
   autocomplete menu, the input coloring, the command chip, and the `/help` card:

   ```js
   { cmd: "/export", label: "Export", desc: "Download this conversation",
     usage: "/export", hint: "Saves the transcript as Markdown.",
     text: "text-sky-600 dark:text-sky-400", chip: "bg-sky-50 text-sky-700 …" },
   ```

2. Handle it in `runCommand()` in `frontend/src/hooks/useCommands.js`, **returning
   `true`** so it doesn't fall through to a chat request:

   ```js
   if (lower.startsWith("/export")) {
     // do the thing, then confirm with a transcript pill:
     addNote("Exported this conversation.");
     return true;
   }
   ```

3. If it needs new inputs (a callback, a setting), thread them through the
   `useCommands({...})` arguments from `ChatWindow.jsx`.

### Add a new settings toggle

1. Add the state + toggler in `frontend/src/hooks/useSettings.js`:

   ```js
   const [autoScrollEnabled, setAutoScrollEnabled] = useState(true);
   // …and in the returned object:
   autoScrollEnabled,
   toggleAutoScroll: () => setAutoScrollEnabled((on) => !on),
   ```

2. Render a row in `frontend/src/components/SettingsModal.jsx` (it already imports
   `Toggle`), and pass the new props where the modal is mounted in `App.jsx`.
3. Pass the flag from `App.jsx` down to whoever consumes it (usually a `ChatWindow`
   prop, then into a hook — see how `prefilterEnabled` flows into `useChatStream`).
   Note these switches are session-only; persist to `localStorage` in `useSettings`
   (like `themeFamily`) if it should survive reloads.
