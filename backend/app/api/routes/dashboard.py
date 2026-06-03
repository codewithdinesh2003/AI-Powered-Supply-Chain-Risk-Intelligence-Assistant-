from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import get_current_user, ok
from app.database.connection import get_db
from app.database.models import (
    Incident,
    QuerySession,
    ResolutionStatus,
    RiskLevel,
    SeverityLevel,
    Supplier,
    User,
)

router = APIRouter()


@router.get("/kpis")
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # ── Active incidents ───────────────────────────────────────────────
    total_incidents = (await db.execute(select(func.count(Incident.id)))).scalar_one()
    open_incidents = (
        await db.execute(
            select(func.count(Incident.id)).where(
                Incident.resolution_status.in_([ResolutionStatus.open, ResolutionStatus.in_progress])
            )
        )
    ).scalar_one()

    # Severity breakdown of open incidents
    severity_rows = (
        await db.execute(
            select(Incident.severity, func.count(Incident.id))
            .where(Incident.resolution_status.in_([ResolutionStatus.open, ResolutionStatus.in_progress]))
            .group_by(Incident.severity)
        )
    ).all()
    by_severity = {r[0].value: r[1] for r in severity_rows}

    # ── Overall risk score ────────────────────────────────────────────
    avg_impact = (
        await db.execute(
            select(func.avg(Incident.impact_score)).where(
                Incident.resolution_status == ResolutionStatus.open
            )
        )
    ).scalar_one()
    # impact_score is stored on 0-100 scale (from ETL risk_score).
    # Never exceed 100; no multiplier needed.
    raw_score = float(avg_impact) if avg_impact is not None else 50.0
    overall_risk_score = round(min(max(raw_score, 0.0), 100.0), 1)

    # ── Supplier health ───────────────────────────────────────────────
    total_suppliers = (await db.execute(select(func.count(Supplier.id)))).scalar_one()
    healthy_suppliers = (
        await db.execute(
            select(func.count(Supplier.id)).where(
                Supplier.risk_level.in_([RiskLevel.low, RiskLevel.medium])
            )
        )
    ).scalar_one()
    supplier_health_pct = round(healthy_suppliers / max(total_suppliers, 1) * 100, 1)
    avg_reliability = (
        await db.execute(select(func.avg(Supplier.reliability_score)))
    ).scalar_one()

    # ── Shipment on-time rate ─────────────────────────────────────────
    # Count all records that have a shipment_status (proxy for "shipment records analyzed")
    total_shipments = (
        await db.execute(
            select(func.count(Incident.id)).where(
                Incident.shipment_status.is_not(None)
            )
        )
    ).scalar_one()
    on_time = (
        await db.execute(
            select(func.count(Incident.id)).where(
                Incident.shipment_status.in_(["On-Time", "Early"])
            )
        )
    ).scalar_one()
    on_time_rate = round(on_time / max(total_shipments, 1) * 100, 1)

    # ── Query sessions today ──────────────────────────────────────────
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    queries_today = (
        await db.execute(
            select(func.count(QuerySession.id)).where(
                QuerySession.created_at >= today_start
            )
        )
    ).scalar_one()

    avg_eval = (
        await db.execute(
            select(func.avg(QuerySession.evaluation_score)).where(
                QuerySession.created_at >= today_start,
                QuerySession.evaluation_score.is_not(None),
            )
        )
    ).scalar_one()

    # ── Recent query sessions ─────────────────────────────────────────
    recent_sessions_result = (
        await db.execute(
            select(QuerySession)
            .order_by(QuerySession.created_at.desc())
            .limit(5)
        )
    )
    recent_sessions = [
        {
            "id": s.id,
            "query_text": s.query_text[:80] + "..." if len(s.query_text) > 80 else s.query_text,
            "risk_score": s.evaluation_score,
            "tokens_used": s.tokens_used,
            "latency_ms": s.latency_ms,
            "created_at": s.created_at.isoformat(),
        }
        for s in recent_sessions_result.scalars().all()
    ]

    return ok(
        {
            "overall_risk_score": overall_risk_score,
            "active_incidents": {
                "total": open_incidents,
                "by_severity": by_severity,
            },
            "supplier_health": {
                "pct_healthy": supplier_health_pct,
                "avg_reliability_score": round(float(avg_reliability or 0), 1),
                "total_suppliers": total_suppliers,
            },
            "shipment_on_time_rate": on_time_rate,
            "shipment_records_analyzed": int(total_shipments),
            "shipment_status_distribution": {
                row[0]: row[1]
                for row in (
                    await db.execute(
                        select(Incident.shipment_status, func.count(Incident.id))
                        .where(Incident.shipment_status.is_not(None))
                        .group_by(Incident.shipment_status)
                    )
                ).all()
                if row[0]
            },
            "ai_queries": {
                "today": queries_today,
                "avg_quality_score": round(float(avg_eval or 0), 2) if avg_eval else None,
            },
            "recent_sessions": recent_sessions,
        }
    )


@router.get("/alerts")
async def get_alerts(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Recent open/high-severity incidents for the alert feed."""
    result = await db.execute(
        select(Incident)
        .where(
            Incident.resolution_status.in_([ResolutionStatus.open, ResolutionStatus.in_progress]),
            Incident.severity.in_([SeverityLevel.critical, SeverityLevel.high, SeverityLevel.medium]),
        )
        .order_by(Incident.occurred_at.desc())
        .limit(limit)
    )
    incidents = result.scalars().all()

    alerts = [
        {
            "id": i.id,
            "incident_code": i.incident_code,
            "title": i.title,
            "severity": i.severity.value,
            "category": i.category.value,
            "supplier_ref": i.supplier_ref,
            "warehouse_location": i.warehouse_location,
            "shipment_status": i.shipment_status,
            "delivery_delay_days": i.delivery_delay_days,
            "impact_score": i.impact_score,
            "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
            "resolution_status": i.resolution_status.value,
        }
        for i in incidents
    ]

    return ok(alerts, meta={"count": len(alerts)})
