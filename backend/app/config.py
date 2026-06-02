from __future__ import annotations

import os
from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI ───────────────────────────────────────────────
    openai_api_key: str

    # ── LangSmith ────────────────────────────────────────────
    langchain_api_key: str = ""
    langchain_tracing_v2: str = "true"
    langchain_project: str = "supply-chain-risk-intel"

    # ── MySQL ────────────────────────────────────────────────
    mysql_url: str  # async: mysql+aiomysql://...
    mysql_url_sync: str = ""  # sync: mysql+pymysql://...  (Alembic only)

    # ── ChromaDB ─────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "supply_chain_incidents"

    # ── JWT ──────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── CORS ─────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── App ──────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    # ── LLM Model Selection ───────────────────────────────────
    llm_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # ── Retrieval Config ─────────────────────────────────────
    retrieval_top_k: int = 10
    retrieval_semantic_k: int = 15
    retrieval_bm25_k: int = 15
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Token Optimization ────────────────────────────────────
    max_context_tokens: int = 100_000   # gpt-4o context limit
    context_compression_threshold: float = 0.80  # compress above 80 % usage

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def configure_langsmith(self) -> None:
        """Push LangSmith env-vars into os.environ so the SDK picks them up."""
        os.environ["LANGCHAIN_API_KEY"] = self.langchain_api_key
        os.environ["LANGCHAIN_TRACING_V2"] = self.langchain_tracing_v2
        os.environ["LANGCHAIN_PROJECT"] = self.langchain_project


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
