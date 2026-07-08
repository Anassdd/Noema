"""The provider-swap layer — the ONLY module allowed to import the OpenAI SDK.

It exposes exactly two capabilities to the rest of the app:

    chat(messages, ...)   -> streamed or buffered chat completion
    embed(texts)          -> embedding vectors

Both providers speak the OpenAI API: `openai` (standard endpoint, dev) and `llmaas`
(an OpenAI-compatible endpoint at a custom base_url — the company's Azure-hosted
gateway, prod). Switching is a config change in config.settings, never a code change.
No other file should construct a client or hardcode a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal, Sequence

from openai import BadRequestError, OpenAI

from app.config import settings

# --- Message / result types ------------------------------------------------

# A chat message is the usual {"role": ..., "content": ...} dict.
Message = dict[str, str]


@dataclass(frozen=True)
class Usage:
    """Token accounting for one chat call (surfaced to the UI per the spec).

    `cached_tokens` is the portion of `prompt_tokens` served from the provider's
    automatic prompt-prefix cache (0 if the endpoint doesn't report it). It's what
    makes Contextual Retrieval cheap — the repeated document prefix is mostly cached.
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int = 0


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

def _build_client() -> OpenAI:
    if settings.provider == "llmaas":
        # OpenAI-compatible endpoint at a custom URL. Keyless gateways still
        # need a non-empty api_key string (the SDK refuses an empty one), so we
        # pass a placeholder the server ignores.
        return OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key or "not-needed",
        )
    return OpenAI(api_key=settings.api_key)


# Single shared client for the process. Every provider is OpenAI-compatible, so
# callers below are provider-agnostic.
_client = _build_client()


def _to_usage(raw) -> Usage | None:
    if not raw:
        return None
    details = getattr(raw, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0 if details is not None else 0
    return Usage(
        prompt_tokens=raw.prompt_tokens,
        completion_tokens=raw.completion_tokens,
        total_tokens=raw.total_tokens,
        cached_tokens=cached,
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


def _create(client: OpenAI | None = None, **kwargs):
    """Create a completion, retrying without params the model rejects.

    Reasoning models (gpt-5, o1/o3/o4...) only allow the default temperature and
    take `max_completion_tokens` instead of the legacy `max_tokens`, so on the
    matching 400 we adapt and retry. Generic by design — no per-model table to
    maintain across providers.
    """
    client = client or _client
    for _ in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            msg = str(exc).lower()
            if "max_tokens" in msg and "max_tokens" in kwargs:
                kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                continue
            if "temperature" in msg and "temperature" in kwargs:
                kwargs.pop("temperature")
                continue
            raise
    return client.chat.completions.create(**kwargs)


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


def transcribe_image(
    image_b64: str,
    prompt: str,
    *,
    model: str | None = None,
    detail: str = "auto",
    max_tokens: int | None = None,
) -> ChatResult:
    """Vision call: send one page image (base64 PNG) + a prompt, get text back.

    Uses the same OpenAI-compatible client as chat(), with the standard image
    content part — so dev and the prod endpoint work through the one swap point.
    temperature=0 for faithful transcription (dropped automatically if the
    model rejects it). `detail` is the vision fidelity ("low"|"high"|"auto"):
    "high" forces max tiling for small/dense text. This is how PDF pages are
    parsed (render → image → here).
    """
    model = model or settings.parse_model or settings.chat_model
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_b64}",
                        "detail": detail,
                    },
                },
            ],
        }
    ]
    resp = _create(**_common_kwargs(model, messages, 0, max_tokens), stream=False)
    return ChatResult(
        text=resp.choices[0].message.content or "",
        usage=_to_usage(resp.usage),
        model=resp.model,
    )


_judge_client: OpenAI | None = None


def judge_chat(
    messages: Sequence[Message],
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> ChatResult:
    """A buffered chat call on the JUDGE endpoint (used only to score bench answers).

    With JUDGE_MODEL/JUDGE_BASE_URL configured this reaches a different,
    OpenAI-compatible endpoint — e.g. Gemini's — so the judge is a different model
    family than the generator (kills self-preference bias). Unset -> falls back to
    the main provider and chat model, so the bench works before any judge key exists.
    """
    global _judge_client
    configured = bool(settings.judge_model and settings.judge_base_url
                      and settings.judge_api_key)
    if not configured:
        # Not (fully) configured -> judge on the main provider. A judge_model
        # WITHOUT a base_url means "different model, same provider"; a base_url
        # without its key means the key isn't pasted yet — don't call a foreign
        # endpoint that will reject us, fall back to the chat model instead.
        model = (settings.judge_model
                 if settings.judge_model and not settings.judge_base_url
                 else settings.chat_model)
        return _chat_buffered(messages, model, temperature, max_tokens)
    if _judge_client is None:
        _judge_client = OpenAI(base_url=settings.judge_base_url,
                               api_key=settings.judge_api_key)
    resp = _create(
        _judge_client,
        **_common_kwargs(settings.judge_model, messages, temperature, max_tokens),
        stream=False,
    )
    return ChatResult(
        text=resp.choices[0].message.content or "",
        usage=_to_usage(resp.usage),
        model=resp.model,
    )


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
