import { useState } from "react";

import { addBelief } from "../api/beliefs.js";
import { NO_MEMORY } from "../api/chat.js";

// Slash-command dispatch — these are handled locally, with no model call.
// `runCommand(text)` returns true when the text was a command (and has been
// handled), or false to let it fall through to a chat request. Also owns the
// /forget confirmation dialog state (multi-match never deletes blindly).
export function useCommands({
  setMessages,
  messages,
  memories,
  memoryEnabled,
  onRemember,
  onSetCharacter,
  onForgetMemory,
  onSettingsQuestion,
  selectedMemory,
  expertEnabled,
}) {
  const [forgetCandidates, setForgetCandidates] = useState([]);

  const addNote = (content) =>
    setMessages((prev) => [...prev, { role: "note", content }]);

  const runCommand = (text) => {
    const trimmed = text.trim();
    const lower = trimmed.toLowerCase();

    // /remember <fact>: store globally and acknowledge locally; the fact then
    // rides along with every future request.
    if (lower.startsWith("/remember")) {
      if (!memoryEnabled) {
        addNote("Memory is off — enable it in settings to save facts.");
        return true;
      }
      const fact = trimmed.slice("/remember".length).trim();
      if (fact) onRemember(fact);
      addNote(
        fact
          ? `Saved to memory: “${fact}”`
          : "Usage: /remember <fact to keep across all chats>",
      );
      return true;
    }

    // /note <text>: append a note to the CURRENT memory context's beliefs (the save
    // selected in the composer, else live memory). Separate from /remember, which stores
    // user facts across all chats — this is domain knowledge the expert weighs vs the sources.
    if (lower.startsWith("/note")) {
      const note = trimmed.slice("/note".length).trim();
      if (!note) {
        addNote("Usage: /note <something to remember in this memory>");
        return true;
      }
      // NO_MEMORY means "answer without memory" — notes still land on the live context.
      const memoryContext = selectedMemory === NO_MEMORY ? null : selectedMemory;
      const where = memoryContext || "Live memory";
      // Send recent turns (role/content only) so the backend can resolve "he"/"that" against
      // the conversation; the claim itself is never changed. The pill shows what was saved.
      const recent = (messages || [])
        .filter((m) => (m.role === "user" || m.role === "assistant") && m.content)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.content }));
      addBelief(note, "default", memoryContext || null, recent)
        .then((res) => {
          const saved = res.note || note;
          addNote(
            expertEnabled
              ? `Noted in “${where}”: “${saved}”`
              : `Noted in “${where}”: “${saved}” — turn on Expert mode to use it in answers.`,
          );
        })
        .catch((e) => addNote(`Couldn't save the note: ${e.message}`));
      return true;
    }

    // /character <description>: set the persona (empty clears it). The header
    // control is the live indicator, so no permanent transcript note.
    if (lower.startsWith("/character")) {
      onSetCharacter(trimmed.slice("/character".length).trim());
      return true;
    }

    // /forget <text>: substring-match saved facts. One match removes it;
    // several open a confirm dialog before removing.
    if (lower.startsWith("/forget")) {
      const query = trimmed.slice("/forget".length).trim().toLowerCase();
      if (!query) {
        addNote("Usage: /forget <part of the fact to remove>");
        return true;
      }
      // Match against the fact's content, not the boilerplate "The user…"
      // prefix every auto-saved fact carries — else "/forget user" matches all.
      const matchable = (fact) =>
        fact.toLowerCase().replace(/^the user('?s)?\b\s*/, "");
      const matches = memories.filter((m) => matchable(m).includes(query));
      if (matches.length === 0) {
        addNote("No saved fact matches that.");
      } else if (matches.length === 1) {
        onForgetMemory(matches);
        addNote(`Forgot: “${matches[0]}”`);
      } else {
        setForgetCandidates(matches);
      }
      return true;
    }

    // /clear: wipe this conversation's transcript (memory/PDFs untouched).
    if (lower === "/clear" || lower.startsWith("/clear ")) {
      setMessages([]);
      return true;
    }

    // /settings <question>: answer an app-usage question with the app guide
    // loaded for that ONE turn (normal chats never carry it).
    if (lower.startsWith("/settings")) {
      const question = trimmed.slice("/settings".length).trim();
      if (!question) {
        addNote(
          "Usage: /settings <your question about the app> — e.g. " +
            "“/settings how do I clear my memory”. The app guide is loaded " +
            "only for that answer.",
        );
        return true;
      }
      onSettingsQuestion(question);
      return true;
    }

    // /help: show the command guide card (rendered locally; filtered out of
    // what's sent to the model).
    if (lower === "/help" || lower.startsWith("/help ")) {
      setMessages((prev) => [...prev, { role: "help", content: "" }]);
      return true;
    }

    return false;
  };

  const confirmForget = (chosen) => {
    onForgetMemory(chosen);
    addNote(`Forgot ${chosen.length} fact${chosen.length > 1 ? "s" : ""}.`);
    setForgetCandidates([]);
  };

  const cancelForget = () => setForgetCandidates([]);

  return { runCommand, forgetCandidates, confirmForget, cancelForget };
}
