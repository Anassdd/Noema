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

// Builds the single system message pinned to the front of every chat request:
// persona (/character) → attached PDFs → long-term memory (profile + now).
// Documents go before memory so the cache-friendly prefix stays stable for the
// whole conversation. Returns null when there's nothing to add.
export function buildSystemMessage(character, memoryContext, documents) {
  const parts = [];

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

  if (!parts.length) return null;
  return { role: "system", content: parts.join("\n\n") };
}
