// Token counting with the real tiktoken encoding, lazily loaded.
//
// The o200k_base tables are ~2 MB of JS — bundling them eagerly tripled the
// app's initial load. Instead the encoder is fetched in the background (its own
// chunk) and counts fall back to the ~4-chars-per-token heuristic until it
// lands (typically well before the user finishes their first message).
//
// Encoding is tied to the model family, NOT the provider — o200k_base covers
// gpt-4o/gpt-5 era models on both OpenAI and Azure. For classic gpt-4 swap the
// import to "gpt-tokenizer/encoding/cl100k_base".
let encode = null;

import("gpt-tokenizer/encoding/o200k_base")
  .then((mod) => {
    encode = mod.encode;
  })
  .catch(() => {
    /* keep the heuristic if the chunk fails to load */
  });

export function estimateTokens(text) {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return encode ? encode(trimmed).length : Math.ceil(trimmed.length / 4);
}
