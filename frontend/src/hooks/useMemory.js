import { useEffect, useState } from "react";

import {
  fetchMemories,
  saveMemory,
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

  // After a turn, let the backend judge what to remember. Returns the facts it
  // added so the chat can confirm them inline.
  const judgeMemory = async (recent) => {
    try {
      const { added, memories: updated } = await autoMemory(recent);
      setMemories(updated);
      return added;
    } catch (err) {
      console.error(err);
      return [];
    }
  };

  return {
    memories,
    addMemory,
    clearMemories,
    removeMemory,
    forgetMemories,
    judgeMemory,
  };
}
