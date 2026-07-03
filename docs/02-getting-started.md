# 02 — Getting started

Install and run: follow the [README quickstart](../README.md#quickstart-macos-dev)
(macOS) or [RUN_ON_WINDOWS.md](../RUN_ON_WINDOWS.md) (Windows/prod). This page is the
**first session** once both servers are up.

## Your first expert (10 minutes)

1. **Ingest** — open `http://localhost:5173/?view=graph`, drop a PDF (or paste text).
   Watch the graph grow page by page; each page also lands in the vector base
   (`rag_indexing` → `rag_done` in the status line).
2. **Inspect** — click nodes (entity summaries), hover edges (facts + validity), drag the
   time scrubber to replay the memory.
3. **Checkpoint** — ⧉ Saves → name it (e.g. `v1`). You can now experiment freely and
   restore anytime.
4. **Chat** — back on `http://localhost:5173/`, open Settings → enable **Expert mode**.
   Ask something the document answers. You get a live reasoning trace, an answer with
   `[S1]` citations, and the sources panel.
5. **Follow up** with a pronoun ("and what about *its* risks?") — the trace shows the
   rewritten standalone query. Ask in French if the corpus is French.
6. **Add your own view** — type `/note I think the report underestimates X`, then ask
   about X: the answer contrasts the sources with your note, attributing each.
7. **Dream** — see the scripted demo in [07 — Dream](07-dream-evolution.md#a-3-minute-demo-that-shows-every-pass)
   (start the backend with `DREAM_GRACE_DAYS=0` for it).

## The slash commands

| Command | Does |
|---|---|
| `/remember <fact>` | save a durable personal fact (all chats) |
| `/note <note>` | add a belief to the current memory context (expert mode) |
| `/character <persona>` | set the assistant's persona for this chat |
| `/forget <hint>` | remove matching personal facts |
| `/clear` | clear personal memory |
| `/help` | list commands |

## Where to go next

- Understand the system: [01 — Overview](01-overview.md), then [04 — Backend tour](04-backend-tour.md).
- Tune it: [03 — Configuration](03-configuration.md).
- Poke the internals visually: [10 — Testing & the lab](10-testing.md).
