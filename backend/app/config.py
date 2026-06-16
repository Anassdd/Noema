"""Central configuration — the ONLY place env vars are read.

Everything is driven by environment variables (loaded from a local .env in dev).
`LLM_PROVIDER` selects the backend at runtime:
  - "openai" : local dev (Mac), personal key.
  - "azure"  : Azure OpenAI (key + endpoint + deployments).
  - "llmaas" : any OpenAI-compatible endpoint at a custom URL, key optional.
Porting providers should be a config change here + filling that provider's vars,
never a code change in the rest of the app.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env from the backend/ folder if present.
load_dotenv()


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

    `chat_model` / `embed_model` are model names on OpenAI and *deployment names*
    on Azure — the rest of the app does not care which, it just passes them to
    the SDK. That uniformity is what keeps llm_client.py the single swap point.
    """

    provider: str  # "openai" | "azure" | "llmaas"

    api_key: str
    chat_model: str
    embed_model: str

    # Azure-only; empty strings on OpenAI.
    azure_endpoint: str = ""
    azure_api_version: str = ""

    # llmaas-only: base URL of a custom OpenAI-compatible endpoint. Empty
    # otherwise. The api_key may be blank for keyless gateways (llm_client
    # supplies a placeholder, which the SDK requires but the server ignores).
    base_url: str = ""

    # Generation defaults (overridable per call in llm_client.chat()).
    chat_temperature: float = 0.2
    # Cap on conversation turns kept in history; consumed by the chat route, not
    # here, but centralised so token-economy knobs live in one place.
    max_history_turns: int = 8


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "openai":
        return Settings(
            provider="openai",
            api_key=_require("OPENAI_API_KEY"),
            chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            embed_model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
            chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
            max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "8")),
        )

    if provider == "azure":
        return Settings(
            provider="azure",
            api_key=_require("AZURE_OPENAI_API_KEY"),
            azure_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
            azure_api_version=_require("AZURE_OPENAI_API_VERSION"),
            # On Azure these are deployment names, not model names.
            chat_model=_require("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            embed_model=_require("AZURE_OPENAI_EMBED_DEPLOYMENT"),
            chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
            max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "8")),
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
            # Optional — only needed once RAG embeddings are wired up.
            embed_model=os.getenv("LLMAAS_EMBED_MODEL", ""),
            chat_temperature=float(os.getenv("CHAT_TEMPERATURE", "0.2")),
            max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "8")),
        )

    raise ConfigError(
        f"Unknown LLM_PROVIDER={provider!r}. Expected 'openai', 'azure', or 'llmaas'."
    )


# Loaded once at import. Fail fast on bad config rather than on first request.
settings = load_settings()
