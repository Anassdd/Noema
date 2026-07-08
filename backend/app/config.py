"""Central configuration — the ONLY place env vars are read.

Everything is driven by environment variables (loaded from a local .env in dev).
`LLM_PROVIDER` selects the backend at runtime:
  - "openai" : local dev (Mac), personal key, standard endpoint.
  - "llmaas" : any OpenAI-compatible endpoint at a custom URL (the company's
               Azure-hosted gateway), key optional.
Porting providers should be a config change here + filling that provider's vars,
never a code change in the rest of the app.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env by its path relative to this file, so it loads regardless of the
# working directory — uvicorn runs from backend/, but the Streamlit lab runs from the
# repo root. find-by-cwd would miss it there.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or inconsistent."""


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"See backend/.env.example."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """Resolved, validated configuration for the selected provider.

    `chat_model` / `embed_model` are whatever name the chosen endpoint expects —
    the rest of the app does not care, it just passes them to the SDK. That
    uniformity is what keeps llm_client.py the single swap point.
    """

    provider: str  # "openai" | "llmaas"

    api_key: str
    chat_model: str
    embed_model: str
    # Vision model/deployment used to parse PDF pages (render→image→Markdown+LaTeX).
    # Should be a strong vision-capable model; falls back to chat_model if unset.
    parse_model: str = ""

    # Parser backend, orthogonal to the LLM provider: "vision" (render→vision LLM,
    # default, works anywhere the LLM does) or "docintel" (Azure Document
    # Intelligence — deterministic, in-tenant, page provenance). Swap via .env.
    parser: str = "vision"
    docintel_endpoint: str = ""  # Azure Document Intelligence endpoint (docintel only)
    docintel_key: str = ""  # Azure Document Intelligence key (docintel only)

    # llmaas-only: base URL of a custom OpenAI-compatible endpoint. Empty
    # otherwise. The api_key may be blank for keyless gateways (llm_client
    # supplies a placeholder, which the SDK requires but the server ignores).
    base_url: str = ""

    # Retrieval: where the embedded vector store persists (empty -> backend/.chroma).
    vector_dir: str = ""
    # User beliefs: where the per-(user, memory-context) note files persist
    # (empty -> backend/.beliefs). Small markdown, injected into answers, not indexed.
    beliefs_dir: str = ""
    # Reranker seam (optional, no-GPU). Empty rerank_model -> a dedicated reranker is
    # not used; the lab/engine can still fall back to LLM-based reranking.
    rerank_model: str = ""
    rerank_base_url: str = ""
    rerank_api_key: str = ""

    # Judge seam (optional) — a separate OpenAI-compatible endpoint used ONLY for
    # scoring bench answers, so the judge can be a different model family than the
    # generator (e.g. Gemini's OpenAI-compatible endpoint on dev). All three unset ->
    # the judge falls back to the main provider + chat model.
    judge_model: str = ""
    judge_base_url: str = ""
    judge_api_key: str = ""

    # Generation defaults (overridable per call in llm_client.chat()).
    chat_temperature: float = 0.2
    # Cap on conversation turns kept in history; consumed by the chat route, not
    # here, but centralised so token-economy knobs live in one place.
    max_history_turns: int = 8


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    # Parser selection + DI creds — orthogonal to the LLM provider, shared by all.
    _common = dict(
        parser=os.getenv("PARSER", "vision").strip().lower(),
        docintel_endpoint=os.getenv("DOCINTEL_ENDPOINT", ""),
        docintel_key=os.getenv("DOCINTEL_KEY", ""),
        vector_dir=os.getenv("VECTOR_DIR", ""),
        beliefs_dir=os.getenv("BELIEFS_DIR", ""),
        rerank_model=os.getenv("RERANK_MODEL", ""),
        rerank_base_url=os.getenv("RERANK_BASE_URL", ""),
        rerank_api_key=os.getenv("RERANK_API_KEY", ""),
        judge_model=os.getenv("JUDGE_MODEL", ""),
        judge_base_url=os.getenv("JUDGE_BASE_URL", ""),
        judge_api_key=os.getenv("JUDGE_API_KEY", ""),
    )

    if provider == "openai":
        return Settings(
            provider="openai",
            api_key=_require("OPENAI_API_KEY"),
            # Default judge/answer model: gpt-5.4-mini — current-gen mini tier, strong
            # routing/grading/reasoning while staying cheap. (Previous default
            # gpt-4.1-mini is deprecated by OpenAI on 2026-11-04.) Override in .env.
            chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.4-mini"),
            # text-embedding-3-large: better retrieval + multilingual (French corpus), still
            # cheap. Dimension is read dynamically downstream, so this is a safe swap.
            embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large"),
            # The STRONG model: vision PDF parsing + graph extraction (quality is
            # load-bearing there — see graph/providers.py).
            parse_model=os.getenv("OPENAI_PARSE_MODEL", "gpt-5.4"),
            chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
            max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "8")),
            **_common,
        )

    if provider == "llmaas":
        return Settings(
            provider="llmaas",
            # Optional: blank for a keyless gateway. llm_client passes a
            # placeholder to the SDK when this is empty.
            api_key=os.getenv("LLMAAS_API_KEY", ""),
            base_url=_require("LLMAAS_BASE_URL"),
            # Model name exactly as the endpoint expects it.
            chat_model=_require("LLMAAS_CHAT_MODEL"),
            parse_model=os.getenv("LLMAAS_PARSE_MODEL")
            or os.getenv("LLMAAS_CHAT_MODEL", ""),
            # Optional — only needed once RAG embeddings are wired up.
            embed_model=os.getenv("LLMAAS_EMBED_MODEL", ""),
            chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
            max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "8")),
            **_common,
        )

    raise ConfigError(
        f"Unknown LLM_PROVIDER={provider!r}. Expected 'openai' or 'llmaas'."
    )


# Loaded once at import. Fail fast on bad config rather than on first request.
settings = load_settings()
