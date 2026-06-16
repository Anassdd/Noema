"""Durable conversations: list summaries, load one, save (upsert), delete.

The frontend generates the conversation id, so PUT is an upsert — it creates the
conversation on first save and updates it thereafter.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import conversation_store
from app.schemas import ConversationRename, ConversationSave

router = APIRouter(prefix="/conversations")


@router.get("")
def list_conversations() -> dict:
    """Lightweight summaries for the sidebar (no message bodies)."""
    return {"conversations": conversation_store.list_summaries()}


@router.delete("", status_code=204)
def clear_conversations() -> None:
    """Delete all conversations (clear history)."""
    conversation_store.clear()


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    """The full conversation, loaded when the user opens it."""
    conv = conversation_store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.put("/{conversation_id}")
def save_conversation(conversation_id: str, body: ConversationSave) -> dict:
    return conversation_store.upsert(
        conversation_id,
        body.title,
        body.character,
        body.messages,
        body.documents,
    )


@router.patch("/{conversation_id}")
def rename_conversation(conversation_id: str, body: ConversationRename) -> dict:
    if not conversation_store.rename(conversation_id, body.title):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conversation_id, "title": body.title}


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str) -> None:
    if not conversation_store.delete(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
