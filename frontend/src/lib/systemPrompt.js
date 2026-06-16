// Builds the single system message pinned to the front of every chat request:
// persona (/character) → attached PDFs → saved facts (/remember). Documents go
// before memory so the cache-friendly prefix stays stable for the whole
// conversation. Returns null when there's nothing to add.
export function buildSystemMessage(character, memories, documents) {
  const parts = [];

  if (character) {
    parts.push(
      `Adopt and stay in the following persona/role for the whole conversation: ${character}`,
    );
  }

  if (documents.length) {
    const names = documents.map((d) => `"${d.filename}"`).join(", ");
    const blocks = documents
      .map(
        (d) =>
          `--- BEGIN DOCUMENT: ${d.filename} ---\n${d.text}\n--- END DOCUMENT ---`,
      )
      .join("\n\n");
    parts.push(
      `The user attached ${documents.length} document(s): ${names}. Treat them as the primary source for questions about them, and if the answer isn't in them, say so.\n\n${blocks}`,
    );
  }

  if (memories.length) {
    parts.push(
      "Facts the user explicitly asked you to remember. Use them when relevant:\n" +
        memories.map((m) => `- ${m}`).join("\n"),
    );
  }

  if (!parts.length) return null;
  return { role: "system", content: parts.join("\n\n") };
}
