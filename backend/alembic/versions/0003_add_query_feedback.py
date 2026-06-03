"""Add query_feedback table.

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_feedback",
        sa.Column("id",             sa.CHAR(36),   nullable=False),
        sa.Column("session_id",     sa.String(255), nullable=False),
        sa.Column("user_id",        sa.String(255), nullable=True),
        sa.Column("overall_rating", sa.Integer(),   nullable=True),
        sa.Column("helpful",        sa.Boolean(),   nullable=True),
        sa.Column("comment",        sa.Text(),      nullable=True),
        sa.Column("created_at",     sa.DateTime(),  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_feedback_session_id", "query_feedback", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_table("query_feedback")
