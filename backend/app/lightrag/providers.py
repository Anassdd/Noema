"""LightRAG ↔ provider-abstraction bridge.

LightRAG takes async LLM/embedding callables at construction; ours go through
app.llm_client (the single provider swap point), so LightRAG's own OpenAI bindings
are never imported and switching OpenAI ↔ the enterprise endpoint stays a config
change. llm_client is sync, so both bridges hop to a thread.
"""

from __future__ import annotations

import asyncio

import numpy as np
from lightrag.utils import EmbeddingFunc

from app import llm_client
from app.config import settings


def extraction_model_name(model: str | None = None) -> str:
    """Entity/relation extraction quality is load-bearing (a weak extractor makes a
    sparse graph), so the default is the STRONG model — same rule as Graphiti's."""
    return model or settings.parse_model or settings.chat_model


def build_llm_func(model: str):
    """An async completion callable in the shape LightRAG expects. Extra kwargs
    (response_format, timeouts…) are accepted and ignored — LightRAG parses replies
    leniently (json_repair), and our provider layer owns generation params."""

    async def complete(prompt: str, system_prompt: str | None = None,
                       history_messages: list[dict] | None = None, **_) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history_messages or [])
        messages.append({"role": "user", "content": prompt})
        res = await asyncio.to_thread(llm_client.chat, messages, model=model, temperature=0.0)
        return res.text or ""

    return complete


_embed_dim: int | None = None


def _embedding_dim() -> int:
    """Probed from the provider once — never assumed, it differs across endpoints."""
    global _embed_dim
    if _embed_dim is None:
        _embed_dim = len(llm_client.embed(["dimension probe"])[0])
    return _embed_dim


def build_embedding_func() -> EmbeddingFunc:
    async def embed(texts: list[str]) -> np.ndarray:
        vecs = await asyncio.to_thread(llm_client.embed, texts)
        return np.array(vecs, dtype=np.float32)

    return EmbeddingFunc(embedding_dim=_embedding_dim(), func=embed)
