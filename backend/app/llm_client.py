"""The provider-swap layer — the ONLY module allowed to import the OpenAI SDK.

It exposes exactly two capabilities to the rest of the app:

    chat(messages, ...)   -> streamed or buffered chat completion
    embed(texts)          -> embedding vectors

Porting from OpenAI to Azure OpenAI is handled entirely here (same SDK, just the
`AzureOpenAI` class + different constructor args), driven by config.settings.
No other file should construct an OpenAI/AzureOpenAI client or hardcode a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal, Sequence

from openai import AzureOpenAI, BadRequestError, OpenAI

from app.config import settings

# --- Message / result types ------------------------------------------------

# A chat message is the usual {"role": ..., "content": ...} dict.
Message = dict[str, str]


@dataclass(frozen=True)
class Usage:
    """Token accounting for one chat call (surfaced to the UI per the spec)."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ChatResult:
    """Return value of a non-streaming chat() call."""

    text: str
    usage: Usage | None
    model: str


@dataclass(frozen=True)
class StreamEvent:
    """One event from a streaming chat() call.

    type="delta"  -> `text` holds the next token(s).
    type="usage"  -> `usage` holds final token counts (arrives once, at the end).
    """

    type: Literal["delta", "usage"]
    text: str = ""
    usage: Usage | None = None


# --- Client construction (the swap point) ----------------------------------

def _build_client() -> OpenAI | AzureOpenAI:
    if settings.provider == "azure":
        return AzureOpenAI(
            api_key=settings.api_key,
            azure_endpoint=settings.azure_endpoint,
            api_version=settings.azure_api_version,
        )
    if settings.provider == "llmaas":
        # OpenAI-compatible endpoint at a custom URL. Keyless gateways still
        # need a non-empty api_key string (the SDK refuses an empty one), so we
        # pass a placeholder the server ignores.
        return OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key or "not-needed",
        )
    return OpenAI(api_key=settings.api_key)


# Single shared client for the process. Both classes expose the same
# `.chat.completions` and `.embeddings` interface, so callers below are
# provider-agnostic.
_client = _build_client()


def _to_usage(raw) -> Usage | None:
    if not raw:
        return None
    return Usage(
        prompt_tokens=raw.prompt_tokens,
        completion_tokens=raw.completion_tokens,
        total_tokens=raw.total_tokens,
    )


# --- Public API ------------------------------------------------------------

def chat(
    messages: Sequence[Message],
    *,
    stream: bool = False,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatResult | Iterator[StreamEvent]:
    """Run a chat completion.

    stream=False -> returns a ChatResult (buffered text + usage).
    stream=True  -> returns an iterator of StreamEvent (deltas, then one usage).

    `model` overrides the configured chat model/deployment; the other kwargs
    override generation defaults. Streaming requests opt into usage reporting so
    the UI can still show token counts after a live answer.
    """
    model = model or settings.chat_model
    temperature = settings.chat_temperature if temperature is None else temperature

    if stream:
        return _chat_stream(messages, model, temperature, max_tokens)
    return _chat_buffered(messages, model, temperature, max_tokens)


def _common_kwargs(model, messages, temperature, max_tokens) -> dict:
    """Shared request kwargs. Only include `max_tokens` when actually set —
    newer models (gpt-5, o-series) reject the legacy `max_tokens` param, even as
    null, so sending it unconditionally breaks them.
    """
    kwargs = {
        "model": model,
        "messages": list(messages),
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return kwargs


def _create(**kwargs):
    """Create a completion, retrying without params the model rejects.

    Reasoning models (gpt-5, o1/o3/o4...) only allow the default temperature, so
    on a temperature-related 400 we drop it and let the model default. Generic
    by design — no per-model table to maintain across providers.
    """
    try:
        return _client.chat.completions.create(**kwargs)
    except BadRequestError as exc:
        if "temperature" in str(exc).lower() and "temperature" in kwargs:
            kwargs.pop("temperature")
            return _client.chat.completions.create(**kwargs)
        raise


def _chat_buffered(messages, model, temperature, max_tokens) -> ChatResult:
    resp = _create(
        **_common_kwargs(model, messages, temperature, max_tokens),
        stream=False,
    )
    return ChatResult(
        text=resp.choices[0].message.content or "",
        usage=_to_usage(resp.usage),
        model=resp.model,
    )


def _chat_stream(messages, model, temperature, max_tokens) -> Iterator[StreamEvent]:
    stream = _create(
        **_common_kwargs(model, messages, temperature, max_tokens),
        stream=True,
        # Without this, the streamed response omits the usage block entirely.
        stream_options={"include_usage": True},
    )
    for chunk in stream:
        # Usage-only chunks carry no choices; delta chunks carry no usage.
        if chunk.choices:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield StreamEvent(type="delta", text=delta.content)
        if chunk.usage:
            yield StreamEvent(type="usage", usage=_to_usage(chunk.usage))


def list_models() -> list[str]:
    """List model ids available at the configured endpoint.

    Works on any OpenAI-compatible provider (they all expose /v1/models). The
    enterprise endpoint returns its own catalogue; OpenAI returns everything
    (including non-chat models), so the caller/UI decides what to show.
    """
    resp = _client.models.list()
    return sorted(m.id for m in resp.data)


def embed(texts: Sequence[str], *, model: str | None = None) -> list[list[float]]:
    """Embed one or more texts, returning a vector per input (order preserved).

    The embedding dimension is whatever the model returns — callers (ingestion)
    must read it dynamically, never assume it, since it differs between OpenAI
    and the enterprise embedding model.
    """
    if not texts:
        return []
    resp = _client.embeddings.create(
        model=model or settings.embed_model,
        input=list(texts),
    )
    # API guarantees results are returned in input order, but sort defensively.
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]
