# Noema — SOTA of Memory & Knowledge UX (2026)

How leading AI products and agent frameworks handle: (1) user-contributed custom knowledge,
(2) user-added PDFs in a chat, (3) personal-memory storage format. Focus: Anthropic, OpenAI,
Google/Gemini, DeepSeek, plus Mem0 / Letta-MemGPT / LangGraph-LangMem.

Method: deep-research harness — 5 search angles → 23 sources fetched → 113 claims → 25
adversarially verified (3-vote). 24 confirmed, 1 refuted. Recommendations are synthesis
(labeled), reasoned from the verified findings. Sources cited inline.

---

## THE VERDICT — what's best (TL;DR)

| Question | The best approach (2026 SOTA) | Why it wins |
|---|---|---|
| **1. User-contributed knowledge** | **Separate, editable, human-readable tier, injected verbatim, kept distinct from the corpus** — the ChatGPT-saved-memories / Letta-blocks / Anthropic-`/memories` pattern. On write, do **light contextualization** (resolve pronouns/refs like Mem0) but **never rewrite the claim**. Surface belief-vs-corpus conflicts, don't resolve them silently. | Preserves user trust, transparency, and provenance; matches every consumer memory product; contradiction = "inter-context conflict" (Xu et al.) that must be shown. **Noema already does this.** |
| **2. User-added PDFs** | **Ephemeral, per-conversation by default; explicit "promote into the corpus" for persistence.** Choose **long-context stuffing when it fits, chunk-and-retrieve when it doesn't**; always emit page/sentence **citations**. | The whole market splits exactly this way (ChatGPT ephemeral uploads vs vector-store KBs; Anthropic doc-block vs Projects-RAG). Size/window is the universal decision rule. |
| **3. Personal-memory format** | **Markdown-primary hybrid** — editable natural-language Markdown as source-of-record, with a **derived** index (vectors/graph) only where querying needs it. **Not pure JSON.** | Consumer/agent products chose text for transparency; frameworks chose JSON for dedup; the reconciling industry pattern is NL-source-of-record + derived structure. Noema already has the derived layers. |

**One-line answer to "what's best":** keep the human's words as editable Markdown, kept separate
from the documents, shown verbatim and contrasted — and derive any structure from it rather than
forcing the human into JSON. That is simultaneously the simplest and the SOTA-aligned choice, and
it's the direction Noema is already built in.

---

## Q1 — User-contributed custom knowledge / corrections

**The universal pattern: a separate, editable, human-readable memory tier, distinct from the
source corpus.** No major system inserts user assertions into the same index as source data
without a distinct tier/label.

| System | How user knowledge is stored | Editable/transparent? |
|---|---|---|
| **ChatGPT** | Two tiers: **saved memories** (explicit, a user-visible bullet list) + **reference chat history** (inferred from past chats). Both injected into context. | Saved memories: yes (view/delete/clear/off). Chat-history layer: **no** — not individually viewable. |
| **Letta / MemGPT** | Labeled **natural-language "memory blocks"** (label · description · value · char-limit). Agent self-edits in place via tools (`memory_replace/append/insert`). Two tiers: in-context **core** (RAM) vs vector-DB **archival** (disk). | Yes — plain readable text prepended to the prompt. The canonical "editable memory" pattern. |
| **Anthropic memory tool** | Client-side **`/memories` directory of freeform files** (docs use `.xml`/`.txt`, no JSON schema). Six ops: view/create/**str_replace**/insert/delete/rename → a fact can be *swapped*, not just appended. **Anthropic does not host it** — you map `/memories` onto real storage. | Yes — file-based, `CLAUDE.md`-style. |
| **Gemini** | Supports in-conversation NL corrections ("Personal Context"). **Google does not document the storage format** — biggest evidence gap. | Capability confirmed; mechanism undocumented. |
| **LangMem / LangGraph** | **Structured JSON**: namespaced JSON docs; **Profile** (one continuously-updated doc) vs **Collection** (many records). Inner `content` is often still plain text. | Query/dedup-oriented, not freeform Markdown. |

**Verbatim vs LLM-normalize (directly your `/note` question):** the field splits.
- **Keep verbatim / editable:** Letta blocks, Anthropic `/memories`, ChatGPT saved memories — optimize for **user trust + transparency**.
- **Extract & normalize:** **Mem0** runs a two-phase pipeline — an LLM extracts salient *standalone* facts (rewriting user text, **resolving pronouns against a running summary + recent messages**), then a second LLM decides ADD/UPDATE/DELETE/NOOP by vector similarity vs existing memories — optimize for **dedup + consistency**.
- *(This is exactly the "conservative contextualization for `/note`" we discussed: Mem0 confirms pronoun-resolution-at-write is real SOTA; the transparency camp says don't over-rewrite. The sweet spot = resolve references, never alter the claim.)*

**Contradiction (belief vs corpus):** the academic frame is **Xu et al., "Knowledge Conflicts
for LLMs: A Survey" (EMNLP 2024)** — a taxonomy of context-memory / **inter-context** /
intra-memory conflict. A user belief injected into context that disagrees with retrieved corpus
chunks is precisely an **inter-context conflict**, which the guidance says to **surface
explicitly, not let the model silently resolve** — validating Noema's "the sources say X, while
your note holds Y."

Sources: OpenAI memory FAQ + reference-saved-memories; letta.com/blog/agent-memory + docs;
claude.com memory-tool docs; blog.google Personal Intelligence; langchain memory docs +
LangMem launch; Mem0 breakdown (Dwarves) + deepwiki; arxiv 2403.08319.

---

## Q2 — User-added PDFs / files in a chat

**The market splits cleanly into two representations, chosen by size/window:**

| Approach | Who | Mechanics | When chosen |
|---|---|---|---|
| **Retrieval knowledge base** | **OpenAI file_search** (Responses/Assistants API) | Parse → chunk → embed → **persistent named vector store**, referenced by ID; semantic+keyword search + rerank at query time. Stores don't expire by default. | Large / persistent corpora. (ChatGPT *in-chat* uploads are ephemeral per-chat.) |
| **Long-context stuffing** | **Anthropic Files API**; **Gemini** | Whole file injected as **input tokens**. Anthropic: create-once/use-many by `file_id`, persists until deleted, **hard-fails past the window** (`400 exceeds context window`). Gemini: 1M–2M window; Google explicitly pitches "**provide everything upfront**" as an alternative to RAG-with-vector-DBs (while conceding RAG "remains valuable"). | Small-enough files; fidelity over recall. |

**Citations/grounding:** **Anthropic Citations API** — attach a PDF as a `document` block with
`citations:{enabled:true}`; Claude auto-chunks into **sentences** and returns the exact
sentences used (or supply custom chunks for your own granularity). Native sentence-level
provenance. (Google's **NotebookLM** is the grounded-with-citations product analog.)

**Nuance:** Anthropic's consumer **Projects** *does* use RAG retrieval for large project
knowledge — so "Anthropic = stuffing" is only true of a raw Messages `document` block.

**DeepSeek: no surviving data** — named in the question but produced no verified claim (gap).

**Decision rule (universal):** fits the window → stuff it (simpler, higher fidelity); too big
or needs to persist → chunk-and-retrieve.

Sources: developers.openai.com file-search; platform.claude.com files + citations;
claude.com/blog citations-api; ai.google.dev long-context.

---

## Q3 — Personal-memory storage format (JSON vs Markdown, directly)

**No single winner — it splits by who's optimizing for what:**

- **Consumer / agent-memory products → editable natural-language text.** Anthropic `/memories`
  files, Letta blocks, ChatGPT saved memories, and **Claude Code's own auto-memory (Markdown +
  YAML frontmatter, per-topic files + a `MEMORY.md` index)** — for **transparency, user
  control, verbatim injection**. *(This is literally the format of Noema's own dev memory.)*
- **Framework SDKs → structured JSON.** LangMem Profile/Collection, LangGraph namespaced JSON
  docs — for **dedup, querying, consistency**.

**Explicit trade-offs:**

| Format | Wins at | Loses at |
|---|---|---|
| **Markdown / NL text** | transparency, hand-editability, verbatim fidelity | dedup, structured query, machine verification |
| **JSON / DB** | dedup, consistency, querying | transparency, user-editability |
| **Vectors** | semantic recall | exactness, editability |
| **Graph** | relationships, multi-hop | write complexity, storage cost |

**Dissent worth noting:** one 2026 practitioner argues Markdown memory **fails at scale** —
plain-text claims can't be verified/tamper-checked/authority-checked when another agent reads
them (e.g. "User 4521 passed KYC" written into a file) — arguing for structured/graph memory in
multi-agent/high-trust settings. Relevant if Noema ever goes multi-agent; less so for a single
user's own notes.

**Reconciling pattern (industry): a natural-language source-of-record + a derived index**
(embeddings/typed fields/graph edges) built *from* it, not hand-authored.

Sources: claude.com memory-tool; letta.com/blog; langchain memory docs; LangMem conceptual
guide; readysolutions Claude-Code auto-memory; mem0/sparkco/dev.to storage-format blogs.

---

## Recommendations mapped to Noema (synthesis)

**(a) User-contributed knowledge → keep it a SEPARATE, provenance-tagged tier; never merge into
the corpus index/graph unlabeled.** Noema's current design — per-memory-context **editable
Markdown beliefs, injected verbatim, contrasted with corpus retrievals** — *is* the
SOTA-aligned pattern (matches ChatGPT saved-memories, Letta core blocks, Anthropic `/memories`).
If you ever want belief *nodes* in Graphiti, tag `source_type="user_belief"` + a trust weight so
provenance stays intact. **Confidence: high.**

**(b) User-added PDFs → ephemeral per-conversation by default, with an explicit "promote into
this save's corpus" action.** The whole market splits ephemeral-chat-upload vs
persistent-KB; the stuff-vs-retrieve choice is size-driven. Noema's **saves are the natural
persistence boundary**: default ephemeral keeps a save bounded (your Phase-2 "don't explode"
goal), promotion is the deliberate curation seam (→ contextual-RAG + Graphiti). Small dropped
PDF → long-context for fidelity; promoted/large → chunk-and-retrieve; emit page/sentence
citations either way. **Confidence: high.**

**(c) Personal memory → Markdown-primary hybrid, NOT pure JSON.** Keep beliefs/preferences as
editable, human-readable Markdown (source-of-record, injected verbatim — matching Anthropic
`/memories`, Letta, ChatGPT) and **derive** structure (embeddings for recall, Graphiti edges for
relationships) only where querying demands it. Noema already has the graph + vector layers, so
Markdown is the missing, correct source-of-record — and it preserves the transparency your
beliefs feature depends on. **Confidence: high.**

---

## Caveats & open questions

- **Time-sensitive.** ChatGPT's memory was reportedly rebuilt in a **June 2026 "Dreaming"**
  update (background synthesis) — the two user-facing controls remain but backend coupling may
  be understated. Anthropic Files API + memory tool are on **beta headers**
  (`files-api-2025-04-14`, `memory_20250818`).
- **Gemini Personal Context format is undocumented** — capability confirmed, storage not.
- **No DeepSeek data** survived verification.
- **ChatGPT "transparent"** applies to saved memories, **not** the inferred chat-history layer.
- **Refuted:** the claim that ChatGPT saved memories are *only* explicit user requests
  auto-managed like-but-unlike custom instructions (1-2 refute) — the boundary is fuzzier.
- The **verbatim-vs-rewrite decision rule** and production **contradiction-surfacing UX** are
  under-evidenced beyond Mem0 (normalize) / Letta-Anthropic (verbatim) and the Xu taxonomy.

---

## Appendix — Full verified findings (raw deep-research record)

Each finding was adversarially verified by a 3-vote panel (needs 2/3 to survive). `vote` shows
the tally. 24/25 confirmed, 1 refuted.

### Verified factual findings

**F1 — ChatGPT: two memory mechanisms.** *(confidence: high; vote: 3-0 ×3, 2-1 ×1)*
ChatGPT implements two distinct user-facing mechanisms — **saved memories** (details the user
asks it to remember) and **reference chat history** (facts inferred from past chats) — both
injected as context and persisting indefinitely unless deleted. Saved memories are fully
user-editable/transparent (view, delete individual, clear all, turn off). The inferred
chat-history layer is **not** individually viewable — less transparent. Third-party RE suggests
memories are surfaced relevance-selectively, not literally every turn.
Sources: help.openai.com/articles/11146739, /8590148.

**F2 — Gemini: in-conversation corrections, undocumented storage.** *(medium; 3-0)*
Gemini supports NL corrections/preferences ("Remember, I prefer window seats") under Personal
Context / Personal Intelligence, but Google's public materials give **no detail** on how these
are persisted, formatted, or separated from other personalization data. Evidence gap, not a
documented design. Source: blog.google/…/personal-intelligence.

**F3 — Letta/MemGPT: editable NL memory blocks + RAM/disk tiers.** *(high; 3-0)*
Stores knowledge as labeled natural-language **memory blocks** (label · description · value ·
char-limit), self-edited in place via tools (memory_replace/append/insert/rethink), in an
OS-inspired two-tier hierarchy: in-context **core** (RAM) vs vector-DB **archival/recall**
(disk). Values are plain readable text (not JSON/vectors) prepended to the prompt. The canonical
"editable memory" pattern; directly analogous to Noema's Markdown beliefs.
Sources: letta.com/blog/agent-memory; docs.letta.com/…/memory-blocks.

**F4 — Anthropic memory tool: client-side `/memories` file directory.** *(high; 3-0)*
Memory = a client-side directory of freeform files under `/memories` (docs' examples use `.xml`
/`.txt`, no fixed JSON schema), editable in place via **six ops** — view, create, str_replace,
insert, delete, rename — so a fact can be *swapped*, not only appended. **Anthropic does not host
it**; the developer's handler maps `/memories` onto real storage. Tool version `memory_20250818`,
GA on Messages API. The file-based `CLAUDE.md`-style pattern most comparable to Noema's beliefs.
Source: docs.claude.com/…/tool-use/memory-tool.

**F5 — LangMem/LangGraph: structured JSON.** *(high; 3-0)*
LangGraph stores long-term memories as **JSON documents** in a store, namespaced (folder-like) +
keyed (file-like), shared across threads. LangMem organizes records with id+content under either
a **Profile** (single continuously-updated doc) or **Collection** (many discrete records) —
framed as a trade-off (profile = compact current-state/in-place updates; collection = higher
recall). Caveat: default collection inner text is still an unstructured string, so "JSON-leaning"
describes the envelope/typed profiles more than every fact.
Sources: docs.langchain.com/…/memory; langchain.com/blog/langmem-sdk-launch; langmem conceptual guide.

**F6 — Contradiction taxonomy (Xu et al., EMNLP 2024).** *(high; 3-0)*
Knowledge conflicts split into **context-memory** (context vs parametric), **inter-context**
(among contextual sources), and **intra-memory** (within parameters). A user belief injected into
context that disagrees with retrieved corpus chunks is an **inter-context conflict** — Noema
should surface it explicitly, not let the model silently resolve it. Source: arxiv 2403.08319.

**F7 — OpenAI file_search = retrieval, not stuffing.** *(high; 3-0 / 2-1)*
File search (Responses API) parses/chunks/embeds uploads into **persistent named vector stores**
(`vector_stores.create(name=…)`) created once and referenced by ID; queries run semantic+keyword
search with reranking + configurable chunk count. API-created stores don't expire by default.
Caveat: OpenAI also supports ephemeral direct-attachment, and ChatGPT in-chat uploads are
per-chat ephemeral — retrieval-vs-ephemeral is the key axis. Source: developers.openai.com/…/tools-file-search.

**F8 — Anthropic Files API = long-context stuffing.** *(high; 3-0)*
The opposite representation: a persistent create-once/use-many resource (referenced by `file_id`,
retained until deleted, workspace-scoped) whose content is injected as **input tokens**, not
chunked/retrieved — proven because content is billed as input tokens and a request **hard-fails**
(`exceeds context window size (400)`) when the file exceeds the window. Nuance: consumer Projects
DOES use RAG for large knowledge bases; a raw Messages `document` block is token-stuffed.
Source: platform.claude.com/…/files.

**F9 — Anthropic Citations API = sentence-level grounding.** *(high; 3-0)*
PDFs/text attach via a `document` block with optional `citations:{enabled:true}`; the Citations
API grounds answers and returns precise references to the exact sentences/passages used, auto-
chunking documents into **sentences** (or developer-supplied custom chunks for controlled
granularity). Sentence-level provenance from user PDFs is native when using Anthropic.
Sources: platform.claude.com/…/files, /citations; claude.com/blog/introducing-citations-api.

**F10 — Gemini positions long-context as a RAG alternative.** *(high; 3-0)*
Google's docs state limited windows "require strategies like… RAG with vector databases… While
these techniques remain valuable in specific scenarios, Gemini's extensive context window invites
a more direct approach: providing all relevant information upfront." Windows are 1M+ (up to 2M).
Independent notes on practical long-context degradation (needle-in-haystack, ~32K effective) qualify
the wisdom, not Google's stated position. Source: ai.google.dev/…/long-context.

### Recommendations (synthesis, mapped to Noema)

**R-a — user knowledge:** keep beliefs a separate, provenance-tagged tier; verbatim Markdown
injected + contrasted with corpus (Noema's current design). If belief nodes ever go into Graphiti,
tag `source_type="user_belief"` + trust weight. *(high)*

**R-b — PDFs:** ephemeral per-conversation by default + explicit promote-into-a-save's-corpus;
size decides stuff-vs-retrieve; emit citations. Saves = the persistence/curation boundary. *(high)*

**R-c — personal memory:** Markdown-primary hybrid, not pure JSON — editable NL source-of-record +
derived index (vectors/Graphiti) where querying demands. *(high)*

### Refuted (did not survive verification)

- *"ChatGPT saved memories are only details the user explicitly tells it to remember, auto-managed
  unlike custom instructions."* — **1-2, refuted.** The explicit-vs-inferred boundary is fuzzier
  than stated. Source: help.openai.com/…/8590148.

### Primary source list

- OpenAI: help.openai.com/articles/11146739 (reference-saved-memories), /8590148 (memory FAQ),
  developers.openai.com/…/tools-file-search.
- Anthropic: docs.claude.com/…/memory-tool, platform.claude.com/…/files, /citations,
  claude.com/blog/introducing-citations-api.
- Google: blog.google/…/personal-intelligence, ai.google.dev/…/long-context.
- Frameworks: letta.com/blog/agent-memory, docs.letta.com/…/memory-blocks,
  docs.langchain.com/…/memory, langchain.com/blog/langmem-sdk-launch, langmem conceptual guide,
  Mem0 breakdown (memo.d.foundation), deepwiki mem0 storage.
- Academic: arxiv 2403.08319 (Knowledge Conflicts survey), 2506.06485, 2506.08938.
- Practitioner: readysolutions (Claude-Code auto-memory), mem0.ai/blog/state-of-ai-agent-memory-2026,
  dev.to (markdown→semantic-graph), sparkco.ai (RAG vs vector vs graph), leoniemonigatti (memory tool).

**Run stats:** 5 angles · 23 sources fetched · 113 claims extracted · 25 verified · 24 confirmed ·
1 refuted · 0 unverified · 13 after synthesis · 105 agent calls.
