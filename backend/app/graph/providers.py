"""Build Graphiti's LLM + embedder clients from the ONE provider source (app.config).

Graphiti requires its own client objects, so this is the single sanctioned place the
graph layer touches model configuration. It reads app.config.settings and nothing
else — keeping OpenAI (dev) ↔ llmaas (prod) a .env switch for the graph, exactly as
llm_client.py does for the rest of the app. No SDK config is scattered elsewhere.
"""

from __future__ import annotations

from app.config import settings
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient


def _api_key() -> str:
    # Keyless gateways (some llmaas deployments) still need a non-empty placeholder.
    return settings.api_key or "not-needed"


def build_llm_client(extract_model: str | None = None):
    """LLM for extraction. Defaults to the strong parse_model — extraction quality
    drives graph quality (a weak extractor yields a sparse, low-value graph)."""
    model = extract_model or settings.parse_model or settings.chat_model
    kw = dict(api_key=_api_key(), model=model, small_model=settings.chat_model)
    if settings.base_url:
        kw["base_url"] = settings.base_url
    config = LLMConfig(**kw)
    # llmaas = a custom OpenAI-compatible endpoint -> the generic client handles a
    # custom base_url and looser structured-output support across providers.
    if settings.provider == "llmaas":
        return OpenAIGenericClient(config=config)
    return OpenAIClient(config=config)


def build_embedder():
    kw = dict(api_key=_api_key(),
              embedding_model=settings.embed_model or "text-embedding-3-small")
    if settings.base_url:
        kw["base_url"] = settings.base_url
    return OpenAIEmbedder(config=OpenAIEmbedderConfig(**kw))
