import { useEffect, useState } from "react";

import {
  fetchMemories,
  fetchMemoryMarkdown,
  saveMemory,
  saveMemoryMarkdown,
  autoMemory,
  clearMemory,
  removeMemoryFact,
} from "../api/memory.js";

// Cross-conversation memory: the facts saved via /remember, persisted server
// side. The returned list from each call is the source of truth.
export function useMemory() {
  const [memories, setMemories] = useState([]);

  useEffect(() => {
    fetchMemories().then(setMemories).catch(console.error);
  }, []);

  const addMemory = async (fact) => {
    try {
      setMemories(await saveMemory(fact));
    } catch (err) {
      console.error(err);
    }
  };

  const clearMemories = async () => {
    if (!window.confirm("Clear all saved memory? This can't be undone.")) return;
    try {
      setMemories(await clearMemory());
    } catch (err) {
      console.error(err);
    }
  };

  const removeMemory = async (fact) => {
    try {
      setMemories(await removeMemoryFact(fact));
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
      if (updated) setMemories(updated);
    } catch (err) {
      console.error(err);
    }
  };

  // After a turn, let the backend judge evolve the memory (add/update/delete +
  // route beliefs). Returns the change set so the chat can confirm it inline.
  const judgeMemory = async (recent, context) => {
    try {
      const result = await autoMemory(recent, context?.domain ?? "default", context?.memory ?? null);
      setMemories(result.memories);
      return result;
    } catch (err) {
      console.error(err);
      return null;
    }
  };

  // The raw memory file, for the panel's markdown editor. Saving refreshes the
  // fact list from whatever bullets the edited file contains.
  const loadMarkdown = () => fetchMemoryMarkdown();
  const saveMarkdown = async (text) => {
    const { markdown, memories: updated } = await saveMemoryMarkdown(text);
    setMemories(updated);
    return markdown;
  };

  return {
    memories,
    addMemory,
    clearMemories,
    removeMemory,
    forgetMemories,
    judgeMemory,
    loadMarkdown,
    saveMarkdown,
  };
}
