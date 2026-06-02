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
    logger.info("Starting Supply Chain Risk Intelligence API (env=%s)", settings.app_env)
    await init_db()
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
    )

    app.include_router(auth.router,          prefix="/api/auth",          tags=["auth"])
    app.include_router(query.router,         prefix="/api/query",         tags=["query"])
    app.include_router(incidents.router,     prefix="/api/incidents",     tags=["incidents"])
    app.include_router(suppliers.router,     prefix="/api/suppliers",     tags=["suppliers"])
    app.include_router(observability.router, prefix="/api/observability", tags=["observability"])
    app.include_router(evaluation.router,    prefix="/api/evaluation",    tags=["evaluation"])
    app.include_router(dashboard.router,     prefix="/api/dashboard",     tags=["dashboard"])

    # ── Health check ──────────────────────────────────────────────────────
    @app.get("/api/health", tags=["health"])
    async def health():
        return {"success": True, "data": {"status": "ok", "service": "supply-chain-risk-intel"}, "meta": {}}

    return app


app = create_app()
