"""Add company_mappings table for saved ETL column mappings.

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_mappings",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("mapping_config", sa.JSON(), nullable=False),
        sa.Column("source_columns", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_by_user_id", sa.CHAR(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", name="uq_company_mappings_company_id"),
    )
    op.create_index("ix_company_mappings_company_id", "company_mappings", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_table("company_mappings")
