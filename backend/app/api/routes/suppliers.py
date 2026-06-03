from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import get_current_user, ok
from app.database.connection import get_db
from app.database.models import Incident, RiskLevel, Supplier, User
from app.schemas.incidents import SupplierResponse

router = APIRouter()


# ── Static routes MUST come before /{supplier_id} to avoid being shadowed ─────

@router.get("/stats/risk-summary")
async def risk_summary(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total = (await db.execute(select(func.count(Supplier.id)))).scalar_one()
    risk_rows = (
        await db.execute(
            select(Supplier.risk_level, func.count(Supplier.id)).group_by(Supplier.risk_level)
        )
    ).all()
    avg_reliability = (
        await db.execute(select(func.avg(Supplier.reliability_score)))
    ).scalar_one()

    return ok(
        {
            "total_suppliers": total,
            "by_risk_level": {r[0].value: r[1] for r in risk_rows},
            "avg_reliability_score": round(float(avg_reliability or 0), 2),
        }
    )


# ── Collection endpoint ───────────────────────────────────────────────────────

@router.get("")
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    risk_level: Optional[str] = None,
    region: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Supplier).order_by(Supplier.reliability_score.asc())

    if risk_level:
        stmt = stmt.where(Supplier.risk_level == RiskLevel(risk_level))
    if region:
        stmt = stmt.where(Supplier.region.ilike(f"%{region}%"))
    if category:
        stmt = stmt.where(Supplier.category.ilike(f"%{category}%"))
    if search:
        stmt = stmt.where(
            Supplier.name.ilike(f"%{search}%") | Supplier.supplier_id.ilike(f"%{search}%")
        )

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    result = await db.execute(stmt.offset(skip).limit(limit))
    suppliers = result.scalars().all()

    return ok(
        [SupplierResponse.model_validate(s).model_dump() for s in suppliers],
        meta={"total": total, "skip": skip, "limit": limit},
    )


# ── Single-resource endpoints (parameterised — must come AFTER static routes) ─

@router.get("/{supplier_id}/history")
async def supplier_history(
    supplier_id: str,
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Supplier).where(
            (Supplier.id == supplier_id) | (Supplier.supplier_id == supplier_id)
        )
    )
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    inc_result = await db.execute(
        select(Incident)
        .where(Incident.supplier_id == supplier.id)
        .order_by(Incident.occurred_at.asc())
        .limit(limit)
    )
    incidents = inc_result.scalars().all()

    history = [
        {
            "date": i.occurred_at.isoformat() if i.occurred_at else None,
            "delivery_delay_days": i.delivery_delay_days,
            "transportation_cost": i.transportation_cost,
            "inventory_level": i.inventory_level,
            "severity": i.severity.value,
            "shipment_status": i.shipment_status,
        }
        for i in incidents
    ]

    return ok(history, meta={"supplier_id": supplier_id, "count": len(history)})


@router.get("/{supplier_id}")
async def get_supplier(
    supplier_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Supplier).where(
            (Supplier.id == supplier_id) | (Supplier.supplier_id == supplier_id)
        )
    )
    supplier = result.scalar_one_or_none()
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")

    inc_result = await db.execute(
        select(Incident)
        .where(Incident.supplier_id == supplier.id)
        .order_by(Incident.occurred_at.desc())
        .limit(10)
    )
    incidents = inc_result.scalars().all()

    return ok(
        {
            **SupplierResponse.model_validate(supplier).model_dump(),
            "recent_incidents": [
                {
                    "id": i.id,
                    "incident_code": i.incident_code,
                    "title": i.title,
                    "severity": i.severity.value,
                    "delivery_delay_days": i.delivery_delay_days,
                    "occurred_at": i.occurred_at.isoformat() if i.occurred_at else None,
                    "resolution_status": i.resolution_status.value,
                }
                for i in incidents
            ],
        }
    )
