"""Noema backend — FastAPI app factory.

Each product surface is one router (system, chat, memory, documents). New
surfaces (graph, ingestion pipeline) slot in as new routers without touching
this file beyond one include.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (bench, beliefs, chat, conversations, documents, graphmem,
                         memory, system, textgraph)


def create_app() -> FastAPI:
    app = FastAPI(title="Noema")

    # Allow the Vite dev frontend to call this API during local development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        system.router,
        chat.router,
        memory.router,
        documents.router,
        conversations.router,
        textgraph.router,
        graphmem.router,
        beliefs.router,
        bench.router,
    ):
        app.include_router(router)

    return app


app = create_app()
