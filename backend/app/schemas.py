"""Request bodies shared across routers. Responses stay plain dicts."""

from __future__ import annotations

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None  # override the configured chat model


class MemoryRequest(BaseModel):
    fact: str


class ConversationSave(BaseModel):
    title: str = ""
    character: str = ""
    messages: list[dict] = []
    documents: list[dict] = []


class ConversationRename(BaseModel):
    title: str
