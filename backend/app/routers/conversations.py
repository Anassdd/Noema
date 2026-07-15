"""Durable conversations: list summaries, load one, save (upsert), delete.

The frontend generates the conversation id, so PUT is an upsert — it creates the
conversation on first save and updates it thereafter. Every endpoint is scoped
to the signed-in user (see conversation_store's visibility rule).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import conversation_store
from app.routers.auth import require_user
from app.schemas import ConversationRename, ConversationSave

router = APIRouter(prefix="/conversations")


@router.get("")
def list_conversations(user: dict = Depends(require_user)) -> dict:
    """Lightweight summaries for the sidebar (no message bodies)."""
    return {
        "conversations": conversation_store.list_summaries(
            user["username"], user["is_guest"]
        )
    }


@router.delete("", status_code=204)
def clear_conversations(user: dict = Depends(require_user)) -> None:
    """Delete all of this user's conversations (clear history)."""
    conversation_store.clear(user["username"], user["is_guest"])


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, user: dict = Depends(require_user)) -> dict:
    """The full conversation, loaded when the user opens it."""
    conv = conversation_store.get(conversation_id, user["username"], user["is_guest"])
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.put("/{conversation_id}")
def save_conversation(
    conversation_id: str, body: ConversationSave, user: dict = Depends(require_user)
) -> dict:
    summary = conversation_store.upsert(
        conversation_id,
        body.title,
        body.character,
        body.messages,
        body.documents,
        user["username"],
        user["is_guest"],
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return summary


@router.patch("/{conversation_id}")
def rename_conversation(
    conversation_id: str, body: ConversationRename, user: dict = Depends(require_user)
) -> dict:
    if not conversation_store.rename(
        conversation_id, body.title, user["username"], user["is_guest"]
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conversation_id, "title": body.title}


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str, user: dict = Depends(require_user)
) -> None:
    if not conversation_store.delete(
        conversation_id, user["username"], user["is_guest"]
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
