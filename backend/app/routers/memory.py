"""Persistent user-fact memory: the facts saved via /remember (manual) and the
LLM judge (/memory/auto). This is distinct from the future document/graph
memory — it stores durable facts about the *user*, not document knowledge.
Scoped to the signed-in account: each user has their own memory file.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import memory_judge, memory_store
from app.routers.auth import require_user
from app.schemas import ChatRequest, MemoryRequest

router = APIRouter(prefix="/memory")


@router.get("")
def get_memory(user: dict = Depends(require_user)) -> dict[str, list[str]]:
    """Return the persisted facts."""
    return {"memories": memory_store.load_memories(user["username"])}


@router.post("")
def add_memory(req: MemoryRequest, user: dict = Depends(require_user)) -> dict[str, list[str]]:
    """Persist a fact and return the updated list."""
    return {"memories": memory_store.add_memory(req.fact, user["username"])}


@router.post("/remove")
def remove_memory(req: MemoryRequest, user: dict = Depends(require_user)) -> dict[str, list[str]]:
    """Remove a single saved fact and return the updated list."""
    return {"memories": memory_store.remove_memory(req.fact, user["username"])}


@router.delete("")
def clear_memory(user: dict = Depends(require_user)) -> dict[str, list[str]]:
    """Clear all saved facts."""
    return {"memories": memory_store.clear_memories(user["username"])}


@router.post("/auto")
def auto_memory(req: ChatRequest, user: dict = Depends(require_user)) -> dict[str, list[str]]:
    """LLM-judged memory: extract durable facts from a recent exchange.

    Returns the facts newly added this turn plus the full list, so the UI can
    both confirm and refresh.
    """
    username = user["username"]
    messages = [m.model_dump() for m in req.messages]
    known = memory_store.load_memories(username)
    added = memory_judge.extract_facts(messages, known)
    for fact in added:
        memory_store.add_memory(fact, username)
    return {"added": added, "memories": memory_store.load_memories(username)}
