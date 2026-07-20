"""Noema backend — FastAPI app factory.

Each product surface is one router (system, chat, memory, documents). New
surfaces (graph, ingestion pipeline) slot in as new routers without touching
this file beyond one include.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import auth_store
from app.routers import (admin, auth, bench, beliefs, chat, conversations,
                         documents, graphmem, lightragmem, memory, system,
                         textgraph)
from app.routers.admin import require_admin
from app.routers.auth import require_user


def create_app() -> FastAPI:
    app = FastAPI(title="Noema")
    # A fresh deployment must be manageable: seed/promote the .env-configured
    # admin account before the first request can arrive.
    auth_store.ensure_default_admin()

    # Allow the Vite dev frontend to call this API during local development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # auth + system (health/models) stay open; every other surface needs a session.
    app.include_router(auth.router)
    app.include_router(system.router)
    for router in (
        chat.router,
        memory.router,
        documents.router,
        conversations.router,
        textgraph.router,
        graphmem.router,
        lightragmem.router,
        beliefs.router,
        admin.router,  # its endpoints add the admin check on top (require_admin)
    ):
        app.include_router(router, dependencies=[Depends(require_user)])

    # The bench spends real money (builds + runs) — admin accounts only, for now.
    app.include_router(bench.router, dependencies=[Depends(require_admin)])

    return app


app = create_app()
