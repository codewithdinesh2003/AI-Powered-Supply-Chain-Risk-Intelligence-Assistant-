from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class IncidentBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    description: Optional[str] = None
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    category: str = Field(..., pattern="^(supplier|shipment|inventory|demand)$")
    supplier_ref: Optional[str] = None
    warehouse_location: Optional[str] = None
    shipment_status: Optional[str] = None
    delivery_delay_days: Optional[float] = None
    transportation_cost: Optional[float] = None
    inventory_level: Optional[float] = None
    demand_forecast: Optional[float] = None
    impact_score: Optional[float] = Field(default=None, ge=0)
    resolution_status: str = Field(default="open", pattern="^(open|in_progress|resolved|closed)$")
    occurred_at: Optional[datetime] = None


class IncidentCreate(IncidentBase):
    incident_code: str = Field(..., min_length=3, max_length=50)


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    resolution_status: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    impact_score: Optional[float] = Field(default=None, ge=0)


class IncidentResponse(IncidentBase):
    id: str
    incident_code: str
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupplierBase(BaseModel):
    supplier_id: str
    name: str
    region: Optional[str] = None
    category: Optional[str] = None
    reliability_score: Optional[float] = Field(default=None, ge=0, le=100)
    avg_delay_days: Optional[float] = None
    active_orders: int = 0
    risk_level: str = "low"


class SupplierResponse(SupplierBase):
    id: str
    last_updated: datetime

    model_config = {"from_attributes": True}
