"""Read/write the user's own notes for a memory context.

A small human-editable markdown per (user, memory-context). Not ingested into the graph or
RAG — the pipeline injects it into the answer prompt so the expert weighs it against the
sources. See app/beliefs.py and pipeline.answer_stream.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import beliefs
from app.pipeline import contextualize_note
from app.routers.auth import require_user

router = APIRouter(prefix="/beliefs")


class BeliefsBody(BaseModel):
    text: str
    domain: str | None = None
    memory: str | None = None
    # Recent chat turns ({role, content}), sent by /note so a mid-conversation note can have
    # its references resolved before saving. Omitted by the panel (freeform, no context).
    messages: list[dict] | None = None


@router.get("")
def get_beliefs(
    domain: str | None = None,
    memory: str | None = None,
    user: dict = Depends(require_user),
) -> dict:
    return {
        "context": beliefs.context_key(domain, memory),
        "text": beliefs.read_beliefs(domain, memory, user["username"]),
    }


@router.post("")
def save_beliefs(body: BeliefsBody, user: dict = Depends(require_user)) -> dict:
    chars = beliefs.write_beliefs(body.text, body.domain, body.memory, user["username"])
    return {"context": beliefs.context_key(body.domain, body.memory), "chars": chars}


@router.post("/add")
def add_belief(body: BeliefsBody, user: dict = Depends(require_user)) -> dict:
    """Append one note (the chat's /note command). Resolves references against the recent chat
    (claim never altered) when messages are provided, then appends. Returns what was saved."""
    note = contextualize_note(body.text, body.messages) if body.messages else body.text
    chars = beliefs.append_belief(note, body.domain, body.memory, user["username"])
    return {"context": beliefs.context_key(body.domain, body.memory), "chars": chars, "note": note}
