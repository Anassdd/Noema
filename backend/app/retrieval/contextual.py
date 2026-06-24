"""Contextual Retrieval (Anthropic) — the contextualization step.

For each chunk, an LLM writes a short blurb situating it within its parent document;
that blurb is prepended to the chunk before it gets embedded and BM25-indexed. Anthropic
reported this cuts retrieval failures ~49% (~67% with a reranker). The document is sent
on every chunk call but sits at the START of the prompt, so repeated calls for the same
document hit automatic prompt-prefix caching — which is what makes it cheap.

Goes through the provider abstraction (llm_client), so OpenAI on dev and the Azure-hosted
endpoint in prod are a `.env` switch. See CONTEXTUAL.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app import llm_client
from app.chunking.base import Chunk

# Anthropic's prompt, with the document FIRST so the prefix is cacheable across chunks.
PROMPT_TEMPLATE = (
    "<document>\n{document}\n</document>\n\n"
    "Here is the chunk we want to situate within the whole document:\n"
    "<chunk>\n{chunk}\n</chunk>\n\n"
    "Please give a short succinct context to situate this chunk within the overall "
    "document for the purposes of improving search retrieval of the chunk. "
    "Answer only with the succinct context and nothing else."
)

# Models sometimes ignore "answer only with the context" and add a lead-in like
# "Here is the context:" or wrap the answer in quotes/fences. Strip that — otherwise
# the noise gets embedded and pollutes retrieval.
_PREAMBLE = re.compile(
    r"^\s*(here\s+is\s+(the\s+)?(a\s+)?(succinct\s+|short\s+)?context[^:]*:|context:|"
    r"the\s+context\s+is:?)\s*",
    re.I,
)


def _clean_context(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```") and t.endswith("```"):
        t = t[3:-3].strip()
    if len(t) >= 2 and t[0] in "\"'`" and t[-1] == t[0]:
        t = t[1:-1].strip()
    return _PREAMBLE.sub("", t).strip()


@dataclass
class ContextualChunk:
    """A chunk plus its situating context. `text` is what gets embedded / BM25-indexed."""

    chunk: Chunk
    context: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0  # prompt tokens served from the prefix cache

    @property
    def text(self) -> str:
        return f"{self.context}\n\n{self.chunk.text}" if self.context else self.chunk.text

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def contextualize_chunk(document_markdown: str, chunk: Chunk, *, model: str | None = None) -> ContextualChunk:
    """One LLM call: whole document (cacheable prefix) + the chunk -> a short context blurb."""
    messages = [{"role": "user",
                 "content": PROMPT_TEMPLATE.format(document=document_markdown, chunk=chunk.text)}]
    res = llm_client.chat(messages, model=model, temperature=0.0)
    usage = res.usage
    return ContextualChunk(
        chunk=chunk,
        context=_clean_context(res.text),
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        cached_tokens=getattr(usage, "cached_tokens", 0) if usage else 0,
    )


def contextualize_chunks(document_markdown: str, chunks, *, model: str | None = None) -> list[ContextualChunk]:
    """Contextualize every chunk of one document. Sequential for now (concurrency later)."""
    return [contextualize_chunk(document_markdown, c, model=model) for c in chunks]
