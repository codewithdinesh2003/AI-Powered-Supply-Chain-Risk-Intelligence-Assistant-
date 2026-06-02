"""Initial schema — create all core tables.

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("analyst", "manager", "admin", name="userrole"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    # ── suppliers ─────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("supplier_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("avg_delay_days", sa.Float(), nullable=True),
        sa.Column("active_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "risk_level",
            sa.Enum("low", "medium", "high", "critical", name="risklevel"),
            nullable=False,
        ),
        sa.Column(
            "last_updated", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", name="uq_suppliers_supplier_id"),
    )
    op.create_index("ix_suppliers_supplier_id", "suppliers", ["supplier_id"], unique=False)

    # ── incidents ─────────────────────────────────────────────────────────
    op.create_table(
        "incidents",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("incident_code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "severity",
            sa.Enum("low", "medium", "high", "critical", name="severitylevel"),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum("supplier", "shipment", "inventory", "demand", name="incidentcategory"),
            nullable=False,
        ),
        sa.Column("supplier_id", sa.CHAR(36), nullable=True),
        sa.Column("supplier_ref", sa.String(50), nullable=True),
        sa.Column("warehouse_location", sa.String(255), nullable=True),
        sa.Column("shipment_status", sa.String(50), nullable=True),
        sa.Column("delivery_delay_days", sa.Float(), nullable=True),
        sa.Column("transportation_cost", sa.Float(), nullable=True),
        sa.Column("inventory_level", sa.Float(), nullable=True),
        sa.Column("demand_forecast", sa.Float(), nullable=True),
        sa.Column("impact_score", sa.Float(), nullable=True),
        sa.Column(
            "resolution_status",
            sa.Enum("open", "in_progress", "resolved", "closed", name="resolutionstatus"),
            nullable=False,
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("chroma_doc_id", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_code", name="uq_incidents_incident_code"),
    )
    op.create_index("ix_incidents_incident_code", "incidents", ["incident_code"], unique=False)
    op.create_index("ix_incidents_supplier_ref", "incidents", ["supplier_ref"], unique=False)

    # ── query_sessions ────────────────────────────────────────────────────
    op.create_table(
        "query_sessions",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("user_id", sa.CHAR(36), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("agent_trace", sa.JSON(), nullable=True),
        sa.Column("retrieval_context", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("langsmith_run_id", sa.String(100), nullable=True),
        sa.Column("evaluation_score", sa.Float(), nullable=True),
        sa.Column(
            "judge_verdict",
            sa.Enum("APPROVED", "NEEDS_REVISION", "REJECTED", name="judgeverdict"),
            nullable=True,
        ),
        sa.Column("deepeval_scores", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_sessions_session_id", "query_sessions", ["session_id"], unique=False)

    # ── audit_logs ────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.CHAR(36), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"], unique=False)

    # ── evaluation_results ────────────────────────────────────────────────
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("answer_relevancy", sa.Float(), nullable=True),
        sa.Column("faithfulness", sa.Float(), nullable=True),
        sa.Column("contextual_recall", sa.Float(), nullable=True),
        sa.Column("contextual_precision", sa.Float(), nullable=True),
        sa.Column("judge_feasibility", sa.Float(), nullable=True),
        sa.Column("judge_specificity", sa.Float(), nullable=True),
        sa.Column("judge_impact", sa.Float(), nullable=True),
        sa.Column("judge_timeline_realism", sa.Float(), nullable=True),
        sa.Column("judge_overall", sa.Float(), nullable=True),
        sa.Column(
            "judge_verdict",
            sa.Enum("APPROVED", "NEEDS_REVISION", "REJECTED", name="judgeverdict"),
            nullable=True,
        ),
        sa.Column("judge_reasoning", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_results_session_id", "evaluation_results", ["session_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("audit_logs")
    op.drop_table("query_sessions")
    op.drop_table("incidents")
    op.drop_table("suppliers")
    op.drop_table("users")
