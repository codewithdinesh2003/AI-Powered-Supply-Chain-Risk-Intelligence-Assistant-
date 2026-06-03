from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database.connection import dispose_engine, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.configure_langsmith()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    # Silence ChromaDB's broken posthog telemetry (harmless version mismatch)
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

    logger.info("Starting Supply Chain Risk Intelligence API (env=%s)", settings.app_env)
    await init_db()

    # ── Preload heavy components once so first request has no cold-start ──
    try:
        # 1. ChromaDB — open persistent store and keep connection alive
        from app.retrieval.vector_store import get_vector_store
        vs = get_vector_store()
        logger.info("ChromaDB ready (%d documents).", vs.count())

        # 2. CrossEncoder reranker — downloads model weights once, keeps in RAM
        from app.retrieval.reranker import _get_model
        _get_model()
        logger.info("CrossEncoder reranker ready.")

        # 3. BM25 index — load from pickle into RAM
        from app.retrieval.bm25_retriever import BM25Retriever
        bm25 = BM25Retriever()
        logger.info("BM25 index ready (loaded=%s).", bm25.is_ready)

        # 4. LangGraph — compile the StateGraph (has overhead on first compile)
        from app.agents.graph import _get_compiled_graph
        _get_compiled_graph()
        logger.info("LangGraph compiled and ready.")

    except Exception as exc:
        logger.warning("Preload step failed (non-fatal): %s", exc)
    yield
    logger.info("Shutting down...")
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Supply Chain Risk Intelligence API",
        description="AI-powered multi-agent supply chain risk analysis system.",
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

    # ── Global exception handlers ─────────────────────────────────────────
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception on %s: %s", request.url, exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": "Internal server error.", "data": None, "meta": {}},
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Resource not found.", "data": None, "meta": {}},
        )

    # ── Routers ───────────────────────────────────────────────────────────
    from app.api.routes import (
        auth,
        dashboard,
        evaluation,
        incidents,
        observability,
        query,
        suppliers,
        upload,
        etl,
    )

    app.include_router(auth.router,          prefix="/api/auth",          tags=["auth"])
    app.include_router(query.router,         prefix="/api/query",         tags=["query"])
    app.include_router(incidents.router,     prefix="/api/incidents",     tags=["incidents"])
    app.include_router(suppliers.router,     prefix="/api/suppliers",     tags=["suppliers"])
    app.include_router(observability.router, prefix="/api/observability", tags=["observability"])
    app.include_router(evaluation.router,    prefix="/api/evaluation",    tags=["evaluation"])
    app.include_router(dashboard.router,     prefix="/api/dashboard",     tags=["dashboard"])
    app.include_router(upload.router,        prefix="/api/upload",        tags=["upload"])
    app.include_router(etl.router,           prefix="/api/etl",           tags=["etl"])

    # ── Health check ──────────────────────────────────────────────────────
    @app.get("/api/health", tags=["health"])
    async def health():
        return {"success": True, "data": {"status": "ok", "service": "supply-chain-risk-intel"}, "meta": {}}

    return app


app = create_app()
