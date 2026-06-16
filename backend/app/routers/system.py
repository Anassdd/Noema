"""Liveness, generation defaults, and the chat-model catalogue."""

from __future__ import annotations

from fastapi import APIRouter

from app import llm_client
from app.config import settings

router = APIRouter()

# Name fragments of model families that don't speak the chat-completions API.
# This is an *exclusion* heuristic on purpose: anything NOT matching stays
# listed, so an unknown enterprise chat model is never hidden.
_NON_CHAT_FRAGMENTS = (
    "embedding", "whisper", "tts", "transcribe", "audio", "image", "dall-e",
    "moderation", "realtime", "search", "codex", "babbage", "davinci",
    "instruct",
)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/models")
def get_models() -> dict:
    """Chat-capable models at the endpoint, plus the configured default.

    Falls back to an empty list (still with the default) if the endpoint can't
    list, so the UI always has something to select.
    """
    try:
        models = [
            m
            for m in llm_client.list_models()
            if not any(fragment in m.lower() for fragment in _NON_CHAT_FRAGMENTS)
        ]
    except Exception:
        models = []
    return {"models": models, "default": settings.chat_model}
