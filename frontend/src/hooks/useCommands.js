import { useState } from "react";

// Slash-command dispatch — these are handled locally, with no model call.
// `runCommand(text)` returns true when the text was a command (and has been
// handled), or false to let it fall through to a chat request. Also owns the
// /forget confirmation dialog state (multi-match never deletes blindly).
export function useCommands({
  setMessages,
  memories,
  memoryEnabled,
  onRemember,
  onSetCharacter,
  onForgetMemory,
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
