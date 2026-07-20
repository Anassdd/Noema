"""Persistent user-fact memory: the facts saved via /remember (manual) and the
LLM judge (/memory/auto). This is distinct from the future document/graph
memory — it stores durable facts about the *user*, not document knowledge.
Scoped to the signed-in account: each user has their own memory file.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import beliefs, memory_judge, memory_store
from app.routers.auth import require_user
from app.schemas import ChatRequest, MemoryMarkdown, MemoryRequest

router = APIRouter(prefix="/memory")


@router.get("")
def get_memory(user: dict = Depends(require_user)) -> dict[str, list[str]]:
    """Return the persisted facts."""
    return {"memories": memory_store.load_memories(user["username"])}


@router.get("/markdown")
def get_markdown(user: dict = Depends(require_user)) -> dict[str, str]:
    """The memory FILE verbatim — the panel edits this as free markdown."""
    return {"markdown": memory_store.load_markdown(user["username"])}


@router.put("/markdown")
def put_markdown(req: MemoryMarkdown, user: dict = Depends(require_user)) -> dict:
    """Overwrite the memory file with the user's edit. Facts are whatever '- '
    bullet lines it contains; everything else is theirs and kept verbatim."""
    memories = memory_store.save_markdown(req.markdown, user["username"])
    return {"markdown": memory_store.load_markdown(user["username"]),
            "memories": memories}


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
def auto_memory(req: ChatRequest, user: dict = Depends(require_user)) -> dict:
    """Automatic memory EVOLUTION from the latest exchange — no explicit command.

    The judge returns structured operations (add / update / delete) against the
    current fact list, plus any domain beliefs the user asserted, which land in
    the beliefs file of the memory context this chat answers from (req.domain /
    req.memory). When the list outgrows the threshold, a consolidation pass
    merges overlap. The response spells out what changed so the UI can confirm.
    """
    username = user["username"]
    messages = [m.model_dump() for m in req.messages]
    known = memory_store.load_memories(username)
    ops = memory_judge.evolve(messages, known)
    memories = memory_store.apply_operations(
        username, ops["add"], ops["update"], ops["delete"])

    for note in ops["beliefs"]:
        beliefs.append_belief(note, req.domain, req.memory, username)

    consolidated = False
    if len(memories) > memory_judge.CONSOLIDATE_AT:
        merged = memory_judge.consolidate(memories)
        if merged is not None:
            memories = memory_store.replace_all(username, merged)
            consolidated = True

    return {
        "added": ops["add"],
        "updated": [new for _old, new in ops["update"]],
        "removed": ops["delete"],
        "beliefs_added": ops["beliefs"],
        "consolidated": consolidated,
        "memories": memories,
    }
