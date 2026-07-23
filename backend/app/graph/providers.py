"""Build Graphiti's LLM + embedder clients from the ONE provider source (app.config).

Graphiti requires its own client objects, so this is the single sanctioned place the
graph layer touches model configuration. It reads app.config.settings and nothing
else — keeping OpenAI (dev) ↔ llmaas (prod) a .env switch for the graph, exactly as
llm_client.py does for the rest of the app. No SDK config is scattered elsewhere.
"""

from __future__ import annotations

from app.config import settings
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient


def _api_key() -> str:
    # Keyless gateways (some llmaas deployments) still need a non-empty placeholder.
    return settings.api_key or "not-needed"


def _reasoning_effort(effort: str | None = None) -> str:
    """Extraction thinking depth — settings.extract_reasoning (default medium:
    relational extraction is analysis-class; KG-construction research shows no
    gain from deeper thinking). Explicit rather than Graphiti's 'auto', which
    resolves to 'minimal' — a value the gpt-5.x families reject."""
    return effort or settings.extract_reasoning or "medium"


def build_llm_client(extract_model: str | None = None, effort: str | None = None):
    """LLM for extraction. Defaults to the strong parse_model — extraction quality
    drives graph quality (a weak extractor yields a sparse, low-value graph)."""
    model = extract_model or settings.parse_model or settings.chat_model
    kw = dict(api_key=_api_key(), model=model, small_model=settings.chat_model)
    if settings.base_url:
        kw["base_url"] = settings.base_url
    config = LLMConfig(**kw)
    # llmaas = a custom OpenAI-compatible endpoint -> the generic client handles a
    # custom base_url and looser structured-output support across providers (and
    # sends no reasoning params, so the effort fix is OpenAI-path only).
    if settings.provider == "llmaas":
        return OpenAIGenericClient(config=config)
    return OpenAIClient(config=config, reasoning=_reasoning_effort(effort))


def build_embedder():
    kw = dict(api_key=_api_key(),
              embedding_model=settings.embed_model or "text-embedding-3-small")
    if settings.base_url:
        kw["base_url"] = settings.base_url
    return OpenAIEmbedder(config=OpenAIEmbedderConfig(**kw))


def build_cross_encoder():
    """Reranker for the graph search recipes that use one (GRAPH_SEARCH_RECIPE=
    cross_encoder). Without this, Graphiti silently builds its own client pointed at
    api.openai.com — a provider leak. Ranks passages by the logprob of a yes/no
    relevance answer, so the endpoint must expose logprobs (OpenAI does; verify on
    the gateway before enabling that recipe in prod)."""
    kw = dict(api_key=_api_key(), model=settings.chat_model)
    if settings.base_url:
        kw["base_url"] = settings.base_url
    return OpenAIRerankerClient(config=LLMConfig(**kw))
