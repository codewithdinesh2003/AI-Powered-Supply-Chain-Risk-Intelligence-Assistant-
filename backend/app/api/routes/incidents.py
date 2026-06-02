from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import get_current_user, ok
from app.database.connection import get_db
from app.database.models import (
    Incident,
    IncidentCategory,
    ResolutionStatus,
    SeverityLevel,
    User,
)
from app.schemas.incidents import IncidentCreate, IncidentResponse, IncidentUpdate

router = APIRouter()


def _apply_filters(stmt, severity, category, supplier_ref, warehouse, resolution):
    if severity:
        stmt = stmt.where(Incident.severity == SeverityLevel(severity))
    if category:
        stmt = stmt.where(Incident.category == IncidentCategory(category))
    if supplier_ref:
        stmt = stmt.where(Incident.supplier_ref == supplier_ref)
    if warehouse:
        stmt = stmt.where(Incident.warehouse_location.ilike(f"%{warehouse}%"))
    if resolution:
        stmt = stmt.where(Incident.resolution_status == ResolutionStatus(resolution))
    return stmt


@router.get("")
async def list_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    severity: Optional[str] = None,
    category: Optional[str] = None,
    supplier_ref: Optional[str] = None,
    warehouse: Optional[str] = None,
    resolution: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Incident).order_by(Incident.occurred_at.desc())
    stmt = _apply_filters(stmt, severity, category, supplier_ref, warehouse, resolution)
    if search:
        stmt = stmt.where(
            Incident.title.ilike(f"%{search}%") | Incident.description.ilike(f"%{search}%")
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    result = await db.execute(stmt.offset(skip).limit(limit))
    incidents = result.scalars().all()

    return ok(
        [IncidentResponse.model_validate(i).model_dump() for i in incidents],
        meta={"total": total, "skip": skip, "limit": limit},
    )


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return ok(IncidentResponse.model_validate(incident).model_dump())


@router.post("", status_code=201)
async def create_incident(
    req: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(Incident).where(Incident.incident_code == req.incident_code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Incident code already exists.")

    incident = Incident(
        id=str(uuid.uuid4()),
        **req.model_dump(),
        severity=SeverityLevel(req.severity),
        category=IncidentCategory(req.category),
        resolution_status=ResolutionStatus(req.resolution_status),
    )
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    return ok(IncidentResponse.model_validate(incident).model_dump())


@router.put("/{incident_id}")
async def update_incident(
    incident_id: str,
    req: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")

    for field, value in req.model_dump(exclude_none=True).items():
        if field == "severity":
            value = SeverityLevel(value)
        if field == "resolution_status":
            value = ResolutionStatus(value)
        setattr(incident, field, value)

    await db.commit()
    await db.refresh(incident)
    return ok(IncidentResponse.model_validate(incident).model_dump())


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    await db.delete(incident)
    await db.commit()


@router.get("/stats/summary")
async def incident_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total = (await db.execute(select(func.count(Incident.id)))).scalar_one()
    open_count = (
        await db.execute(
            select(func.count(Incident.id)).where(
                Incident.resolution_status.in_(
                    [ResolutionStatus.open, ResolutionStatus.in_progress]
                )
            )
        )
    ).scalar_one()

    # Severity breakdown
    severity_rows = (
        await db.execute(
            select(Incident.severity, func.count(Incident.id)).group_by(Incident.severity)
        )
    ).all()
    severity_counts = {row[0].value: row[1] for row in severity_rows}

    return ok(
        {
            "total": total,
            "open": open_count,
            "by_severity": severity_counts,
        }
    )
