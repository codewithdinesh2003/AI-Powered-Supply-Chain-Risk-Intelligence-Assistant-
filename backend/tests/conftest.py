"""Pytest configuration — adds backend/ to sys.path and sets env vars."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make sure "app" is importable from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide minimal env vars so pydantic-settings doesn't fail at import
os.environ.setdefault("OPENAI_API_KEY", "test-key-placeholder")
os.environ.setdefault("MYSQL_URL", "mysql+aiomysql://user:pass@localhost:3306/test_db")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("LANGCHAIN_API_KEY", "test-ls-key")
os.environ.setdefault("CHROMA_PERSIST_DIR", "/tmp/test_chroma")
