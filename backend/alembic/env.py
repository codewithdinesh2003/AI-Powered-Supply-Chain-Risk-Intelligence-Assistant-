from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Make sure the app package is importable ───────────────────────────────────
# alembic/env.py sits inside backend/alembic/, so we need backend/ on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env before importing Settings so pydantic-settings can read values.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.config import get_settings  # noqa: E402
from app.database.models import Base  # noqa: E402, F401 — registers metadata

# ─────────────────────────────────────────────────────────────────────────────

config = context.config

# Apply Python logging config from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy target metadata (all ORM models must be imported above)
target_metadata = Base.metadata


def _get_sync_url() -> str:
    """Return a *synchronous* MySQL URL for Alembic (uses pymysql driver)."""
    settings = get_settings()
    sync_url = settings.mysql_url_sync
    if not sync_url:
        # Auto-derive sync URL from async URL by replacing the driver portion
        sync_url = settings.mysql_url.replace(
            "mysql+aiomysql://", "mysql+pymysql://"
        )
    return sync_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live DB)."""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the DB)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_sync_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
