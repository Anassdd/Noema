import { useEffect, useState } from "react";

import {
  fetchMemory,
  saveMemory,
  saveMemoryFile,
  autoMemory,
  clearMemory,
  removeMemoryFact,
} from "../api/memory.js";

const EMPTY = { memories: [], context: null, files: null, usage: null };

// Cross-conversation memory: the three-file store (profile / now / history)
// persisted server side. Every API call returns the full state — held here as
// the single source of truth for the fact list, the injection context and the
// settings file editor.
export function useMemory() {
  const [state, setState] = useState(EMPTY);

  // Mount = session start: the fetch also runs the backend's daily expiry
  // sweep, so "in Paris until Sept 1" retires itself the day after.
  useEffect(() => {
    fetchMemory().then(setState).catch(console.error);
  }, []);

  const addMemory = async (fact) => {
    try {
      setState(await saveMemory(fact));
    } catch (err) {
      console.error(err);
    }
  };

  const clearMemories = async () => {
    if (!window.confirm("Clear all saved memory (including history)? This can't be undone.")) return;
    try {
      setState(await clearMemory());
    } catch (err) {
      console.error(err);
    }
  };

  const removeMemory = async (fact) => {
    try {
      setState(await removeMemoryFact(fact));
    } catch (err) {
      console.error(err);
    }
  };

  // Remove several facts at once (/forget). Awaited sequentially so the final
  // response reflects every removal; state is set once at the end.
  const forgetMemories = async (facts) => {
    try {
      let updated;
      for (const fact of facts) updated = await removeMemoryFact(fact);
      if (updated) setState(updated);
    } catch (err) {
      console.error(err);
    }
  };

  // After a turn, let the backend judge evolve the memory (add/update/retire/
  // move + route beliefs). Returns the change set so the chat can confirm it.
  const judgeMemory = async (recent, context) => {
    try {
      const result = await autoMemory(recent, context?.domain ?? "default", context?.memory ?? null);
      setState(result.state);
      return result;
    } catch (err) {
      console.error(err);
      return null;
    }
  };

  // One memory file edited in the settings — facts are its "- " bullets,
  // surrounding prose is kept verbatim. Returns the new state so the editor
  // can adopt the server-normalized text.
  const saveFile = async (name, text) => {
    const next = await saveMemoryFile(name, text);
    setState(next);
    return next;
  };

  return {
    ...state,
    // The first fetch resolved — until then the context is "unknown", not
    // "empty", and the chat must not freeze an empty block into a conversation.
    ready: state.files !== null,
    addMemory,
    clearMemories,
    removeMemory,
    forgetMemories,
    judgeMemory,
    saveFile,
  };
}
