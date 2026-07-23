"""The conversation itself: streamed answers (SSE) and auto-titling."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import llm_client, memory_judge, memory_store, pipeline
from app.config import settings
from app.routers.auth import require_user
from app.schemas import ChatRequest

router = APIRouter()


def _sse(event_type: str, payload: dict) -> str:
    """Format one Server-Sent Event frame: `data: <json>\\n\\n`.

    The JSON carries an event `type` so the frontend can tell deltas apart from
    the final usage event.
    """
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


def _with_recall(messages: list[dict], req: ChatRequest, username: str) -> list[dict]:
    """Server-side archive recall — in-process file scoring, no extra round-trip.

    Lexical (IDF) scoring first, on every recalling turn. When the message is
    EXPLICITLY past-referential and lexical scoring finds nothing, one small
    query-expansion call bridges paraphrase and language gaps ("the Turkish
    trip" → istanbul) — the only case where a miss would be a hard failure.
    Hits ride as one transient system message just before the question."""
    if not req.recall or not messages or messages[-1]["role"] != "user":
        return messages
    question = messages[-1]["content"]
    lines = memory_store.recall(username, question, wide=req.recall_wide)
    if not lines and req.recall_wide:
        keywords = memory_judge.expand_query(question)
        if keywords:
            lines = memory_store.recall(
                username, f"{question} {' '.join(keywords)}", wide=True)
    if not lines:
        return messages
    note = {
        "role": "system",
        "content": (
            "From the user's memory archive (past facts and past conversations) — "
            "use only what is relevant; retrieved sources, when present, take "
            "precedence:\n" + "\n".join(lines)
        ),
    }
    return messages[:-1] + [note, messages[-1]]


def _trim_history(messages: list[dict]) -> list[dict]:
    """Cap the conversation at the configured number of recent turns.

    System messages (persona / documents / memory) always stay; only the
    user/assistant turns are capped, keeping the most recent ones — the
    token-economy rule that history must not grow unbounded.
    """
    system = [m for m in messages if m["role"] == "system"]
    turns = [m for m in messages if m["role"] != "system"]
    keep = settings.max_history_turns * 2  # one turn = user + assistant
    return system + turns[-keep:]


@router.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(require_user)) -> StreamingResponse:
    """Stream the answer as Server-Sent Events.

    With `use_memory` off it's plain chat: `delta` token events then a `usage`
    event. With `use_memory` on it runs the expert pipeline (route → retrieve →
    grade → answer → verify) and additionally streams `status` events (the live
    runtime trace) and a `sources` event (what the answer is grounded on). A
    provider error mid-stream becomes an `error` event, not a dead connection.
    """
    messages = _trim_history([m.model_dump() for m in req.messages])
    # Off-loop: the rare expansion fallback makes an LLM call, and even the
    # fast path reads files — neither belongs on the event loop.
    messages = await asyncio.to_thread(_with_recall, messages, req, user["username"])
    # Sanitize the composer's effort pick — an unknown value must never reach the API.
    effort = req.effort if req.effort in ("none", "low", "medium", "high", "xhigh") else None

    if (req.retrieval or "") == "web":
        # Web mode works with or without a memory selection — it never touches the
        # stores, so it takes its own path before the memory branch.
        async def web() -> AsyncIterator[str]:
            try:
                async for ev in pipeline.web_answer_stream(messages, model=req.model):
                    yield _sse(ev.pop("type"), ev)
            except Exception as exc:
                yield _sse("error", {"message": str(exc)})
            yield "data: [DONE]\n\n"

        return StreamingResponse(web(), media_type="text/event-stream")

    if not req.use_memory:
        def plain() -> Iterator[str]:
            try:
                for event in llm_client.chat(messages, stream=True, model=req.model,
                                             reasoning=effort or settings.chat_reasoning):
                    if event.type == "delta":
                        yield _sse("delta", {"text": event.text})
                    elif event.type == "usage":
                        yield _sse("usage", {"usage": event.usage.__dict__ if event.usage else None})
            except Exception as exc:  # surface provider errors to the UI
                yield _sse("error", {"message": str(exc)})
            yield "data: [DONE]\n\n"

        # Starlette runs a sync generator in a threadpool, so this won't block the loop.
        return StreamingResponse(plain(), media_type="text/event-stream")

    async def expert() -> AsyncIterator[str]:
        try:
            async for ev in pipeline.answer_stream(
                messages, model=req.model, domain_id=req.domain or "default",
                memory=req.memory, retrieval=req.retrieval or "hybrid",
                user=user["username"], effort=effort,
            ):
                yield _sse(ev.pop("type"), ev)
        except Exception as exc:  # surface any pipeline/provider error to the UI
            yield _sse("error", {"message": str(exc)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(expert(), media_type="text/event-stream")


@router.post("/title")
def title(req: ChatRequest) -> dict[str, str]:
    """Name a conversation from its first exchange (cheap buffered call)."""
    transcript = "\n".join(f"{m.role}: {m.content[:300]}" for m in req.messages)
    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": "Give a 3-5 word title for this conversation. Write it in "
                "the language the user's messages are WRITTEN in — judge only by the "
                "words themselves, never by names, nationalities or topics (a user "
                "named Anas writing in English gets an English title). If the language "
                "is mixed or unclear, use English. "
                "Reply with the title only — no quotes, no punctuation at the end.",
            },
            {"role": "user", "content": transcript},
        ],
        stream=False,
        max_tokens=16,
        reasoning="low",
    )
    return {"title": result.text.strip().strip('"')}
