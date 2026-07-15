// Client for the durable conversation store (SQLite on the backend). The
// sidebar loads lightweight summaries; a conversation's full messages + PDFs
// load only when opened. Saving is an upsert keyed by the conversation id.
import { API_BASE, authFetch } from "./client.js";

export async function listConversations() {
  const res = await authFetch(`${API_BASE}/conversations`);
  if (!res.ok) throw new Error(`Failed to load conversations: HTTP ${res.status}`);
  const data = await res.json();
  return data.conversations ?? [];
}

export async function getConversation(id) {
  const res = await authFetch(`${API_BASE}/conversations/${id}`);
  if (!res.ok) throw new Error(`Failed to load conversation: HTTP ${res.status}`);
  return res.json();
}

export async function saveConversation(conversation) {
  const res = await authFetch(`${API_BASE}/conversations/${conversation.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: conversation.title,
      character: conversation.character,
      messages: conversation.messages,
      documents: conversation.documents,
    }),
  });
  if (!res.ok) throw new Error(`Failed to save conversation: HTTP ${res.status}`);
  return res.json(); // the updated summary
}

export async function renameConversation(id, title) {
  const res = await authFetch(`${API_BASE}/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to rename conversation: HTTP ${res.status}`);
  }
}

export async function deleteConversation(id) {
  const res = await authFetch(`${API_BASE}/conversations/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete conversation: HTTP ${res.status}`);
  }
}

export async function clearConversations() {
  const res = await authFetch(`${API_BASE}/conversations`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to clear conversations: HTTP ${res.status}`);
}
