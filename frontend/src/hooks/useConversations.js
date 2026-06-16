import { useEffect, useRef, useState } from "react";

import { fetchTitle } from "../api/title.js";
import {
  listConversations,
  getConversation,
  saveConversation,
  renameConversation,
  deleteConversation as apiDeleteConversation,
  clearConversations,
} from "../api/conversations.js";

const SAVE_DEBOUNCE_MS = 800;

const makeConversation = () => ({
  id: crypto.randomUUID(),
  title: "",
  messages: [],
  character: "",
  documents: [],
});

// Don't persist a brand-new, untouched chat — avoids empty rows piling up.
const isPersistable = (c) =>
  c.messages.length > 0 || c.documents.length > 0 || !!c.character;

// The sidebar list: saved conversations, with the full active one spliced over
// its slot (so its title can fall back to the first message and update live).
// An active chat that isn't saved yet only appears once it has been started —
// a brand-new empty chat stays out of the sidebar until the first message.
const mergeActive = (summaries, active) => {
  if (!active) return summaries;
  if (summaries.some((s) => s.id === active.id)) {
    return summaries.map((s) => (s.id === active.id ? active : s));
  }
  return isPersistable(active) ? [active, ...summaries] : summaries;
};

// Owns the conversations: lightweight summaries for the sidebar plus the one
// fully-loaded active conversation. Loads lazily from the backend and saves
// edits back (debounced) so everything survives reloads.
export function useConversations() {
  const [summaries, setSummaries] = useState([]);
  const [active, setActive] = useState(null);
  const [activeId, setActiveId] = useState(null);

  const saveTimer = useRef(null);
  const pendingSave = useRef(null); // latest active awaiting a debounced save
  const skipSave = useRef(false); // set when active changes from load/switch

  const flushSave = () => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    const conv = pendingSave.current;
    pendingSave.current = null;
    if (conv && isPersistable(conv)) {
      saveConversation(conv)
        .then((summary) =>
          setSummaries((prev) => [
            summary,
            ...prev.filter((s) => s.id !== summary.id),
          ]),
        )
        .catch(console.error);
    }
  };

  const scheduleSave = (conv) => {
    pendingSave.current = conv;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(flushSave, SAVE_DEBOUNCE_MS);
  };

  // Persist edits to the active conversation, but not the change that merely
  // loads or switches it in.
  useEffect(() => {
    if (skipSave.current) {
      skipSave.current = false;
      return;
    }
    if (active && isPersistable(active)) scheduleSave(active);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // Initial load: fetch the saved conversations for the sidebar, but open a
  // fresh empty chat (which stays out of the sidebar until it's started).
  useEffect(() => {
    const startFresh = () => {
      const fresh = makeConversation();
      setActive(fresh);
      setActiveId(fresh.id);
    };
    listConversations()
      .then((list) => setSummaries(list))
      .catch(console.error)
      .finally(startFresh);
  }, []);

  const selectConversation = async (id) => {
    if (id === activeId) return;
    flushSave();
    setActiveId(id);
    try {
      const full = await getConversation(id);
      skipSave.current = true;
      setActive(full);
    } catch (err) {
      console.error(err);
    }
  };

  const newChat = () => {
    flushSave();
    const conv = makeConversation();
    setActive(conv);
    setActiveId(conv.id);
  };

  const deleteConversation = async (id) => {
    flushSave();
    apiDeleteConversation(id).catch(console.error);
    const remaining = summaries.filter((s) => s.id !== id);
    setSummaries(remaining);
    if (id !== activeId) return;
    if (remaining.length) {
      selectConversation(remaining[0].id);
    } else {
      const fresh = makeConversation();
      setActive(fresh);
      setActiveId(fresh.id);
    }
  };

  // Delete every conversation and drop back to a fresh empty chat. Cancels any
  // pending save first so an in-flight debounce can't re-create a row.
  const clearAll = async () => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
    pendingSave.current = null;
    try {
      await clearConversations();
    } catch (err) {
      console.error(err);
    }
    setSummaries([]);
    const fresh = makeConversation();
    setActive(fresh);
    setActiveId(fresh.id);
  };

  // Apply a patch (computed from the current conversation) to the active one.
  const patchActive = (compute) =>
    setActive((prev) => (prev ? { ...prev, ...compute(prev) } : prev));

  const setActiveMessages = (updater) =>
    patchActive((c) => ({
      messages: typeof updater === "function" ? updater(c.messages) : updater,
    }));

  const setActiveDocuments = (updater) =>
    patchActive((c) => ({
      documents: typeof updater === "function" ? updater(c.documents) : updater,
    }));

  // Also strip stale "Character set/reset" notes — the persona badge is the
  // single live indicator, so those shouldn't linger in the transcript.
  const setActiveCharacter = (value) =>
    patchActive((c) => ({
      character: value,
      messages: c.messages.filter(
        (m) =>
          !(
            m.role === "note" &&
            (m.content.startsWith("Character set:") ||
              m.content.startsWith("Character reset"))
          ),
      ),
    }));

  // Name the conversation from its first exchange. Persists by id (so the title
  // sticks even if you've switched away during the title call), updates the
  // sidebar immediately, and refreshes the active view if it's still open.
  const autoTitle = async (exchange) => {
    const id = activeId;
    let title;
    try {
      title = await fetchTitle(exchange);
    } catch (err) {
      console.error(err); // keep the fallback title (first user message)
      return;
    }
    if (!title) return;

    setActive((prev) => (prev && prev.id === id ? { ...prev, title } : prev));
    setSummaries((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    renameConversation(id, title).catch(console.error);
  };

  return {
    conversations: mergeActive(summaries, active),
    activeId,
    active,
    newChat,
    deleteConversation,
    clearAll,
    selectConversation,
    setActiveMessages,
    setActiveDocuments,
    setActiveCharacter,
    autoTitle,
  };
}
