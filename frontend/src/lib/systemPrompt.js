import { estimateTokens } from "./tokens.js";

// Chat-attached PDFs are ephemeral and stuffed into the prompt — the SOTA "it fits → provide it
// upfront" path. Anthropic's Contextual Retrieval guidance: a knowledge base under ~200K tokens
// (~500 pages) can go straight in the prompt with no RAG, paired with prompt caching (which
// OpenAI applies automatically to this stable system-prefix — docs sit before memory — so
// re-sending each turn is cheap, not the cost problem it looks like). Above that, retrieval is the
// right tool → we route the user to the Graph Memory page, which indexes with Contextual Retrieval
// (embed + BM25 over LLM-situated chunks). Budget is on the TOTAL of all attached docs (the
// "knowledge base"), not per file. Default sits below Anthropic's 200K line to keep headroom for
// history/answer and to hold answer quality (lost-in-the-middle) on smaller models — LOWER it if
// the deployed model's context window is small. Env-configurable; set 0 to disable stuffing.
export const DOC_STUFF_MAX_TOKENS = Number(
  import.meta.env.VITE_DOC_STUFF_MAX_TOKENS ?? 150000,
);

export function documentsTokens(documents) {
  return documents.reduce((sum, d) => sum + estimateTokens(d.text), 0);
}

export function documentsFit(documents) {
  return documentsTokens(documents) <= DOC_STUFF_MAX_TOKENS;
}

// The app's self-knowledge: what Noema tells the user when asked how to use or
// configure it. STATIC and identical for every user and conversation — placed
// first in the system message so the whole fleet of chats shares one cached
// prefix. Kept in lockstep with the real UI (commands.js, MessageInput modes,
// SettingsModal, the memory/graph pages) — never describe a control that
// doesn't exist.
const APP_GUIDE = `You are Noema, a domain-expert assistant with document-grounded, source-citing answers and a persistent personal memory. When the user asks how to use or configure the app, answer concretely from this guide — never invent controls:

- Header: the brain icon opens the Memory page in a new tab (?view=memory) — four hand-editable files (Profile, Now, History, Journal) with usage gauges, refresh, dark/light toggle and "Clear all". The graph icon opens the Graph memory page (?view=graph) — upload documents into the expert corpus, browse it in 3D, switch engines, and edit the per-domain Notes (pencil icon). The file icon shows this chat's attached PDFs. Sun/moon toggles dark mode; the model picker is top right.
- Settings (gear at the bottom of the sidebar): theme family (Aurora / Codex) + dark mode; Expert mode (ground answers in the uploaded corpus — off = plain chat); Memory (capture facts + inject them — off = neither); Memory files editor; auto-capture pre-filter; live token estimate; Clear memory. Admins also get account management (Manage ↗, or ?view=admin) and the eval Bench (?view=bench).
- Composer: "+" attaches a PDF to this conversation only; the memory selector chooses the answer context (Live memory, a saved snapshot, or "No memory" = plain chat); the mode selector chooses retrieval — Hybrid (default), Vector only, Graph only, LightRAG, or Web search where available.
- Slash commands: /remember saves a fact about the user, /forget removes one, /note records a domain opinion the expert weighs against sources, /character sets this conversation's persona, /clear wipes this transcript only, /help shows the command guide.
- Memory behavior: fact-bearing messages are captured automatically (a notification appears above the composer); profile topics are woven prose, time-bound facts expire on their end date into History, each chat gets a daily Journal line, and deleting a chat removes its journal lines. Notes belong to the domain and are shared between the live memory and its saves.`;

// Builds the single system message pinned to the front of every chat request:
// app guide → persona (/character) → attached PDFs → long-term memory. Ordered
// most-static-first so the cache-friendly prefix survives the whole
// conversation (the guide is even shared across conversations).
export function buildSystemMessage(character, memoryContext, documents) {
  const parts = [APP_GUIDE];

  if (character) {
    parts.push(
      `Adopt and stay in the following persona/role for the whole conversation: ${character}`,
    );
  }

  if (documents.length) {
    const names = documents.map((d) => `"${d.filename}"`).join(", ");
    if (documentsFit(documents)) {
      const blocks = documents
        .map(
          (d) =>
            `--- BEGIN DOCUMENT: ${d.filename} ---\n${d.text}\n--- END DOCUMENT ---`,
        )
        .join("\n\n");
      parts.push(
        `The user attached ${documents.length} document(s): ${names}. Treat them as the primary source for questions about them, and if the answer isn't in them, say so.\n\n${blocks}`,
      );
    } else {
      // Combined size exceeds the budget — don't overflow the window. Make the model say so
      // rather than pretend it read them, and point the user at the retrieval path.
      parts.push(
        `The user attached ${documents.length} document(s) (${names}) that are too large to include here in full, so you cannot see their contents. Tell the user to add these documents on the Graph Memory page so they get indexed and retrievable, and only answer what you can without their text.`,
      );
    }
  }

  if (memoryContext) {
    const today = new Date().toISOString().slice(0, 10);
    parts.push(
      "Long-term memory about the user (they are the implicit subject of every " +
        "note): topic sections about who they are; \"Now\" — their current situation " +
        "as dated facts (\"→ date\" = until when a fact holds); \"Recent chats\" — what " +
        "you two discussed lately. Today is " + today + " — weave this into your " +
        "answers naturally, and treat facts past their end date as over:\n\n" +
        memoryContext,
    );
  }

  return { role: "system", content: parts.join("\n\n") };
}
