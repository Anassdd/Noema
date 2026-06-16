"""The conversation itself: streamed answers (SSE) and auto-titling."""

from __future__ import annotations

import json
from typing import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app import llm_client
from app.config import settings
from app.schemas import ChatRequest

router = APIRouter()


def _sse(event_type: str, payload: dict) -> str:
    """Format one Server-Sent Event frame: `data: <json>\\n\\n`.

    The JSON carries an event `type` so the frontend can tell deltas apart from
    the final usage event.
    """
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


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
def chat(req: ChatRequest) -> StreamingResponse:
    """Stream the answer as Server-Sent Events.

    Yields one `delta` event per token chunk, then a single `usage` event with
    final token counts. A provider error mid-stream becomes an `error` event
    rather than a silently dead connection. RAG comes in a later slice.
    """
    messages = _trim_history([m.model_dump() for m in req.messages])

    def event_stream() -> Iterator[str]:
        try:
            for event in llm_client.chat(
                messages,
                stream=True,
                model=req.model,
            ):
                if event.type == "delta":
                    yield _sse("delta", {"text": event.text})
                elif event.type == "usage":
                    yield _sse(
                        "usage",
                        {"usage": event.usage.__dict__ if event.usage else None},
                    )
        except Exception as exc:  # surface provider errors to the UI
            yield _sse("error", {"message": str(exc)})
        yield "data: [DONE]\n\n"  # clean end-of-stream sentinel

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/title")
def title(req: ChatRequest) -> dict[str, str]:
    """Name a conversation from its first exchange (cheap buffered call)."""
    transcript = "\n".join(f"{m.role}: {m.content[:300]}" for m in req.messages)
    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": "Give a 3-5 word title for this conversation. "
                "Reply with the title only — no quotes, no punctuation at the end.",
            },
            {"role": "user", "content": transcript},
        ],
        stream=False,
        max_tokens=16,
    )
    return {"title": result.text.strip().strip('"')}
