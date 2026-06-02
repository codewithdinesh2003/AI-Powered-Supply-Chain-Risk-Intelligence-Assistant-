from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database.connection import dispose_engine, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.configure_langsmith()
    logging.basicConfig(level=settings.log_level.upper())

    logger.info("Starting Supply Chain Risk Intelligence API...")
    await init_db()

    yield

    logger.info("Shutting down...")
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Supply Chain Risk Intelligence API",
        description="AI-powered supply chain risk analysis with multi-agent LangGraph orchestration.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers — registered here as they are implemented in later steps ──
    # from app.api.routes import auth, query, incidents, suppliers, observability, evaluation
    # app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    # app.include_router(query.router, prefix="/api/query", tags=["query"])
    # app.include_router(incidents.router, prefix="/api/incidents", tags=["incidents"])
    # app.include_router(suppliers.router, prefix="/api/suppliers", tags=["suppliers"])
    # app.include_router(observability.router, prefix="/api/observability", tags=["observability"])
    # app.include_router(evaluation.router, prefix="/api/evaluation", tags=["evaluation"])

    @app.get("/api/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": "supply-chain-risk-intel"}

    return app


app = create_app()
