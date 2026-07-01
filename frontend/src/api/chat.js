// Talks to the backend's POST /chat, which streams Server-Sent Events.
//
// Why not the native EventSource API? It only supports GET and can't send a
// JSON body. So we POST with fetch and parse the text/event-stream frames off
// the ReadableStream by hand — frames are separated by a blank line ("\n\n"),
// each carries one `data: <json>` line.

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/**
 * Stream a chat completion.
 *
 * @param {Array<{role: string, content: string}>} messages  full conversation
 * @param {object} handlers
 * @param {(text: string) => void}  handlers.onDelta  called per token chunk
 * @param {(usage: object|null) => void} handlers.onUsage final token counts
 * @param {(step: {stage: string, detail: string}) => void} [handlers.onStatus] runtime-trace step
 * @param {(sources: object[]) => void} [handlers.onSources]  the answer's cited sources
 * @param {AbortSignal} [handlers.signal]  to cancel an in-flight stream
 * @param {string} [handlers.model]  model id to use (defaults server-side)
 * @param {boolean} [handlers.useMemory]  ground the answer in the RAG/graph memory
 * @param {string} [handlers.domain]  which knowledge base to ground in
 * @param {string|null} [handlers.memory]  a saved snapshot name to answer from (null = live)
 */
export async function streamChat(
  messages,
  { onDelta, onUsage, onStatus, onSources, signal, model, useMemory = false, domain = "default", memory = null },
) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, model, use_memory: useMemory, domain, memory }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Drain every complete frame currently in the buffer; keep the remainder.
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep).trim();
      buffer = buffer.slice(sep + 2);

      if (!frame.startsWith("data:")) continue;
      const data = frame.slice(5).trim();

      if (data === "[DONE]") return; // clean end-of-stream sentinel

      let event;
      try {
        event = JSON.parse(data);
      } catch {
        continue; // skip a malformed frame rather than killing the stream
      }

      if (event.type === "delta") onDelta(event.text);
      else if (event.type === "usage") onUsage(event.usage);
      else if (event.type === "status") onStatus?.(event); // live runtime trace step
      else if (event.type === "sources") onSources?.(event.sources); // cited sources
      // Provider error mid-stream — surface it instead of ending silently.
      else if (event.type === "error")
        throw new Error(event.message || "The model returned an error.");
    }
  }
}
