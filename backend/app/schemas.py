"""Request bodies shared across routers. Responses stay plain dicts."""

from __future__ import annotations

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # override the configured chat model
    domain: str | None = None  # which knowledge base to ground answers in
    memory: str | None = None  # a saved snapshot name to answer from (None = live memory)
    use_memory: bool = True  # ground answers in the RAG/graph memory (off = plain chat)
    retrieval: str | None = None  # "hybrid" (default) | "rag" | "graph" | "lightrag" — which store answers
    recall: bool = False  # search the personal archive (history+journal) for this turn
    recall_wide: bool = False  # the message explicitly references the past (lower bar)
    effort: str | None = None  # reasoning depth for THIS answer (composer selector)


class MemoryRequest(BaseModel):
    fact: str


class MemoryMarkdown(BaseModel):
    markdown: str


class Credentials(BaseModel):
    username: str
    password: str


class AdminRename(BaseModel):
    username: str


class AdminPassword(BaseModel):
    password: str


class AdminFlag(BaseModel):
    is_admin: bool


class ConversationSave(BaseModel):
    title: str = ""
    character: str = ""
    messages: list[dict] = []
    documents: list[dict] = []


class ConversationRename(BaseModel):
    title: str
