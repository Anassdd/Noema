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

    # Consolidated state root (STORAGE.md §3). Empty = every store keeps its
    # historical location; set (e.g. "backend/var") = all state defaults move under
    # it. Individual overrides below still win. Adopt via scripts/migrate_state.py.
    state_dir: str = ""
    # Usernames treated as admins regardless of their stored flag (comma-separated,
    # case-insensitive). The escape hatch for accounts created before the admin flag
    # existed, and for locking yourself out. Normal admin rights live on the records.
    admin_users: str = ""
    # Default admin account, guaranteed to exist at every startup — so any
    # deployment is manageable out of the box: admin/admin until the password is
    # changed in-app (an existing account is promoted, never re-passworded, so
    # the change sticks). Set ADMIN_PASSWORD= (empty) to disable seeding.
    admin_username: str = "admin"
    admin_password: str = "admin"
    # Retrieval: where the embedded vector store persists (empty -> backend/.chroma).
    vector_dir: str = ""
    # LightRAG: where its file-based stores persist (empty -> backend/data/lightrag).
    lightrag_dir: str = ""
    # User beliefs: where the per-(user, memory-context) note files persist
    # (empty -> backend/.beliefs). Small markdown, injected into answers, not indexed.
    beliefs_dir: str = ""
    # Reranker seam (optional, no-GPU). Empty rerank_model -> a dedicated reranker is
    # not used; the lab/engine can still fall back to LLM-based reranking.
    rerank_model: str = ""
    rerank_base_url: str = ""
    rerank_api_key: str = ""
    # Retrieval-time reranking of fused candidates: "llm" (RankGPT-style, one cheap call
    # through the normal chat endpoint — works on dev and the gateway), "endpoint" (the
    # dedicated reranker above), or "off". The single biggest published retrieval win.
    retrieval_rerank: str = "llm"

    # Contextualizer guard (see retrieval/contextual.py). Documents at/under the cap are
    # situated against the WHOLE document (Anthropic's recipe verbatim); larger ones
    # against head+region excerpts of ~context_part_tokens. Default 250k = the GPT-5
    # family's usable input (272k) minus headroom; drop to ~100k on a 128k-context model.
    context_doc_cap: int = 250_000
    context_part_tokens: int = 48_000
    # Blurb calls per prompt-prefix group run 1 (cache-priming) + this many in parallel.
    # 1 = fully sequential; raise only within the API key's rate-limit comfort.
    context_concurrency: int = 4

    # Judge seam (optional) — a separate OpenAI-compatible endpoint used ONLY for
    # scoring bench answers, so the judge can be a different model family than the
    # generator (e.g. Gemini's OpenAI-compatible endpoint on dev). With only a model
    # set (the default), verdicts run on the MAIN provider with that model — Sol:
    # the strongest grader available and a different generation than the mini
    # answerer; verdicts are tiny so the tier costs little. Set base_url+key to
    # move judging to a foreign endpoint instead.
    judge_model: str = "gpt-5.6-sol"
    judge_base_url: str = ""
    judge_api_key: str = ""
    # Thinking cap for the judge. Verdicts are two-field JSONs — a reasoning judge
    # (e.g. gemini-3.5-flash) burning thinking tokens on them multiplies bench wall
    # time for nothing. "none" disables thinking; set JUDGE_REASONING= (empty) to
    # send no cap at all. Dropped automatically if the endpoint rejects it.
    judge_reasoning: str = "none"

    # Provider-side web search (the OpenAI web_search tool via the Responses API).
    # The searching runs on the PROVIDER's servers — nothing but the normal API
    # call leaves this machine, so corporate proxies are never in the path. OFF by
    # default on llmaas (bank gateways may not pass the tool through; flip
    # WEB_SEARCH=on to try), on for the dev openai provider. The bench NEVER uses
    # it — web mode exists only as an explicit chat retrieval choice.
    web_search: bool = False

    # Generation defaults (overridable per call in llm_client.chat()).
    chat_temperature: float = 0.2
    # Cap on conversation turns kept in history; consumed by the chat route, not
    # here, but centralised so token-economy knobs live in one place.
    max_history_turns: int = 8


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    # Parser selection + DI creds — orthogonal to the LLM provider, shared by all.
    _common = dict(
        state_dir=os.getenv("NOEMA_STATE_DIR", "").strip(),
        admin_users=os.getenv("ADMIN_USERS", ""),
        admin_username=os.getenv("ADMIN_USERNAME", "admin").strip(),
        admin_password=os.getenv("ADMIN_PASSWORD", "admin"),
        parser=os.getenv("PARSER", "vision").strip().lower(),
        docintel_endpoint=os.getenv("DOCINTEL_ENDPOINT", ""),
        docintel_key=os.getenv("DOCINTEL_KEY", ""),
        vector_dir=os.getenv("VECTOR_DIR", ""),
        lightrag_dir=os.getenv("LIGHTRAG_DIR", ""),
        beliefs_dir=os.getenv("BELIEFS_DIR", ""),
        rerank_model=os.getenv("RERANK_MODEL", ""),
        rerank_base_url=os.getenv("RERANK_BASE_URL", ""),
        rerank_api_key=os.getenv("RERANK_API_KEY", ""),
        retrieval_rerank=(os.getenv("RETRIEVAL_RERANK", "llm").strip().lower() or "llm"),
        context_doc_cap=int(os.getenv("CONTEXT_DOC_CAP", "250000")),
        context_part_tokens=int(os.getenv("CONTEXT_PART_TOKENS", "48000")),
        context_concurrency=int(os.getenv("CONTEXT_CONCURRENCY", "4")),
        judge_model=os.getenv("JUDGE_MODEL", "gpt-5.6-sol"),
        judge_base_url=os.getenv("JUDGE_BASE_URL", ""),
        judge_api_key=os.getenv("JUDGE_API_KEY", ""),
        judge_reasoning=os.getenv("JUDGE_REASONING", "none"),
        web_search=(os.getenv("WEB_SEARCH", "on" if provider == "openai" else "off")
                    .strip().lower() == "on"),
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
            # load-bearing there — see graph/providers.py). Terra: 5.5-class quality
            # at gpt-5.4's exact price — a free upgrade for the compounding role.
            parse_model=os.getenv("OPENAI_PARSE_MODEL", "gpt-5.6-terra"),
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


def state_path(sub: str, legacy) -> "Path":
    """A state artifact's default home: `<NOEMA_STATE_DIR>/<sub>` when the consolidated
    root is set, else the historical `legacy` location — so adopting the clean layout
    is a config change, never a code change. Explicit per-store env vars still win at
    the call sites."""
    from pathlib import Path

    if settings.state_dir:
        return Path(settings.state_dir) / sub
    return Path(legacy)
