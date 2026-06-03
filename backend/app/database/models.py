from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Enums ────────────────────────────────────────────────────────────────────


class SeverityLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentCategory(str, enum.Enum):
    supplier = "supplier"
    shipment = "shipment"
    inventory = "inventory"
    demand = "demand"


class ResolutionStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class UserRole(str, enum.Enum):
    analyst = "analyst"
    manager = "manager"
    admin = "admin"


class JudgeVerdict(str, enum.Enum):
    approved = "APPROVED"
    needs_revision = "NEEDS_REVISION"
    rejected = "REJECTED"


# ── Base ─────────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Models ───────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.analyst
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    query_sessions: Mapped[list[QuerySession]] = relationship(
        "QuerySession", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    supplier_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reliability_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_delay_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    active_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel), nullable=False, default=RiskLevel.low
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    incidents: Mapped[list[Incident]] = relationship(
        "Incident", back_populates="supplier"
    )

    __table_args__ = (UniqueConstraint("supplier_id", name="uq_suppliers_supplier_id"),)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    incident_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Classification
    severity: Mapped[SeverityLevel] = mapped_column(
        Enum(SeverityLevel), nullable=False, default=SeverityLevel.medium
    )
    category: Mapped[IncidentCategory] = mapped_column(
        Enum(IncidentCategory), nullable=False, default=IncidentCategory.supplier
    )

    # Supplier linkage
    supplier_id: Mapped[Optional[str]] = mapped_column(
        CHAR(36), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    supplier_ref: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True
    )

    # Logistics
    warehouse_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipment_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    delivery_delay_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transportation_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inventory_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    demand_forecast: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Impact
    impact_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Resolution
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        Enum(ResolutionStatus), nullable=False, default=ResolutionStatus.open
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # ChromaDB doc reference (for linking back to vector store)
    chroma_doc_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    supplier: Mapped[Optional[Supplier]] = relationship(
        "Supplier", back_populates="incidents"
    )

    __table_args__ = (
        UniqueConstraint("incident_code", name="uq_incidents_incident_code"),
    )


class QuerySession(Base):
    """Stores every query + full agent trace for observability and history."""

    __tablename__ = "query_sessions"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    query_text: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON blobs from agents / retrieval
    agent_trace: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    retrieval_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Observability
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    langsmith_run_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Quality
    evaluation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_verdict: Mapped[Optional[JudgeVerdict]] = mapped_column(
        Enum(JudgeVerdict), nullable=True
    )
    deepeval_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[Optional[User]] = relationship(
        "User", back_populates="query_sessions"
    )


class AuditLog(Base):
    """Immutable append-only log of user actions for compliance."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, name="metadata"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped[Optional[User]] = relationship("User", back_populates="audit_logs")


class EvaluationResult(Base):
    """Stores DeepEval + LLM-judge evaluation results per query session."""

    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    # DeepEval metrics (0-1)
    answer_relevancy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    faithfulness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contextual_recall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contextual_precision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # LLM-judge scores (0-10)
    judge_feasibility: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_specificity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_impact: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_timeline_realism: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_overall: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    judge_verdict: Mapped[Optional[JudgeVerdict]] = mapped_column(
        Enum(JudgeVerdict), nullable=True
    )
    judge_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class CompanyMapping(Base):
    """Saved LLM-detected column mappings per company for automatic re-use."""

    __tablename__ = "company_mappings"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mapping_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_columns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        CHAR(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("company_id", name="uq_company_mappings_company_id"),)
