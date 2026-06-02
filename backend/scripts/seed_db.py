#!/usr/bin/env python
"""Seed MySQL with a minimal set of suppliers and incidents for development.

Usage:
    python scripts/seed_db.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.database.connection import get_db_session, init_db  # noqa: E402
from app.database.models import (  # noqa: E402
    Incident,
    IncidentCategory,
    ResolutionStatus,
    RiskLevel,
    SeverityLevel,
    Supplier,
    User,
    UserRole,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

# ── Seed data ────────────────────────────────────────────────────────────────

SUPPLIERS = [
    dict(supplier_id="SUP-001", name="GlobalTech Components", region="Asia-Pacific",
         category="Electronics", reliability_score=72.0, avg_delay_days=4.5,
         active_orders=23, risk_level=RiskLevel.medium),
    dict(supplier_id="SUP-002", name="Pacific Rim Manufacturing", region="Asia-Pacific",
         category="Raw Materials", reliability_score=45.0, avg_delay_days=12.3,
         active_orders=8, risk_level=RiskLevel.critical),
    dict(supplier_id="SUP-003", name="EuroLogistics Partners", region="Europe",
         category="Logistics", reliability_score=88.0, avg_delay_days=1.2,
         active_orders=41, risk_level=RiskLevel.low),
    dict(supplier_id="SUP-004", name="NorAm Supply Chain", region="North America",
         category="Packaging", reliability_score=65.0, avg_delay_days=6.7,
         active_orders=17, risk_level=RiskLevel.high),
    dict(supplier_id="SUP-005", name="Gulf Region Distributors", region="Middle East",
         category="Manufacturing", reliability_score=58.0, avg_delay_days=9.1,
         active_orders=12, risk_level=RiskLevel.high),
    dict(supplier_id="SUP-006", name="Andean Resources Ltd", region="South America",
         category="Raw Materials", reliability_score=79.0, avg_delay_days=3.4,
         active_orders=19, risk_level=RiskLevel.low),
    dict(supplier_id="SUP-007", name="Southeast Asia Textiles", region="Asia-Pacific",
         category="Manufacturing", reliability_score=61.0, avg_delay_days=7.8,
         active_orders=31, risk_level=RiskLevel.high),
    dict(supplier_id="SUP-008", name="Nordic Cold Chain", region="Europe",
         category="Logistics", reliability_score=92.0, avg_delay_days=0.8,
         active_orders=55, risk_level=RiskLevel.low),
    dict(supplier_id="SUP-009", name="Midwest Components Inc", region="North America",
         category="Electronics", reliability_score=70.0, avg_delay_days=5.0,
         active_orders=28, risk_level=RiskLevel.medium),
    dict(supplier_id="SUP-010", name="Bay Area Tech Supplies", region="North America",
         category="Electronics", reliability_score=83.0, avg_delay_days=2.1,
         active_orders=37, risk_level=RiskLevel.low),
]

INCIDENTS = [
    dict(incident_code="INC-00001", title="Critical Port Congestion — Shanghai",
         description="Major congestion at Shanghai port causing 18-day delays for electronics components.",
         severity=SeverityLevel.critical, category=IncidentCategory.shipment,
         supplier_id="SUP-001", warehouse_location="Shanghai, China",
         shipment_status="Delayed", delivery_delay_days=18.0,
         transportation_cost=45000.0, inventory_level=120.0, demand_forecast=800.0,
         impact_score=9.2, resolution_status=ResolutionStatus.in_progress,
         days_ago=5),
    dict(incident_code="INC-00002", title="Supplier Reliability Degradation",
         description="Pacific Rim Manufacturing has missed 4 consecutive delivery windows due to labor disputes.",
         severity=SeverityLevel.critical, category=IncidentCategory.supplier,
         supplier_id="SUP-002", warehouse_location="Manila, Philippines",
         shipment_status="Critical", delivery_delay_days=22.0,
         transportation_cost=38000.0, inventory_level=50.0, demand_forecast=500.0,
         impact_score=9.8, resolution_status=ResolutionStatus.open,
         days_ago=3),
    dict(incident_code="INC-00003", title="Inventory Stockout Risk — Electronics",
         description="Current inventory of PCBs at 15% of safety stock level with demand surge of 40%.",
         severity=SeverityLevel.high, category=IncidentCategory.inventory,
         supplier_id="SUP-001", warehouse_location="Los Angeles, USA",
         shipment_status="In-Transit", delivery_delay_days=7.5,
         transportation_cost=12000.0, inventory_level=200.0, demand_forecast=1500.0,
         impact_score=7.5, resolution_status=ResolutionStatus.open,
         days_ago=2),
    dict(incident_code="INC-00004", title="Transportation Cost Spike — Fuel Surcharge",
         description="Fuel surcharges have increased transportation costs by 35% on North America routes.",
         severity=SeverityLevel.medium, category=IncidentCategory.shipment,
         supplier_id="SUP-004", warehouse_location="Chicago, USA",
         shipment_status="In-Transit", delivery_delay_days=2.0,
         transportation_cost=28000.0, inventory_level=950.0, demand_forecast=800.0,
         impact_score=5.0, resolution_status=ResolutionStatus.in_progress,
         days_ago=7),
    dict(incident_code="INC-00005", title="Demand Surge — Holiday Season",
         description="Q4 demand forecast exceeds current supply capacity by 65% across all categories.",
         severity=SeverityLevel.high, category=IncidentCategory.demand,
         supplier_id="SUP-003", warehouse_location="Rotterdam, Netherlands",
         shipment_status="On-Time", delivery_delay_days=0.0,
         transportation_cost=8500.0, inventory_level=300.0, demand_forecast=900.0,
         impact_score=8.0, resolution_status=ResolutionStatus.open,
         days_ago=1),
    dict(incident_code="INC-00006", title="Geopolitical Risk — Trade Route Disruption",
         description="New tariffs imposed on Middle East imports affecting 12% of procurement budget.",
         severity=SeverityLevel.high, category=IncidentCategory.supplier,
         supplier_id="SUP-005", warehouse_location="Dubai, UAE",
         shipment_status="Customs-Hold", delivery_delay_days=11.0,
         transportation_cost=52000.0, inventory_level=180.0, demand_forecast=400.0,
         impact_score=7.8, resolution_status=ResolutionStatus.open,
         days_ago=4),
]

DEFAULT_ADMIN = dict(
    email="admin@scm-intel.local",
    full_name="SCM Admin",
    role=UserRole.admin,
)


# ── Seeding logic ────────────────────────────────────────────────────────────

async def seed() -> None:
    await init_db()
    logger.info("Database tables verified.")

    supplier_pk_map: dict[str, str] = {}

    async with get_db_session() as session:
        from sqlalchemy import select

        # ── Suppliers ──────────────────────────────────────────────────────
        for s in SUPPLIERS:
            result = await session.execute(
                select(Supplier).where(Supplier.supplier_id == s["supplier_id"])
            )
            if result.scalar_one_or_none():
                logger.info("Supplier %s already exists, skipping.", s["supplier_id"])
                result2 = await session.execute(
                    select(Supplier).where(Supplier.supplier_id == s["supplier_id"])
                )
                existing = result2.scalar_one()
                supplier_pk_map[s["supplier_id"]] = existing.id
                continue

            pk = str(uuid.uuid4())
            supplier_pk_map[s["supplier_id"]] = pk
            session.add(Supplier(id=pk, **s))
            logger.info("Seeded supplier: %s", s["name"])

        # ── Admin user ──────────────────────────────────────────────────────
        from passlib.context import CryptContext

        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        result = await session.execute(
            select(User).where(User.email == DEFAULT_ADMIN["email"])
        )
        if not result.scalar_one_or_none():
            session.add(
                User(
                    id=str(uuid.uuid4()),
                    hashed_password=pwd_ctx.hash("Admin@123"),
                    **DEFAULT_ADMIN,
                )
            )
            logger.info("Seeded admin user: %s (password: Admin@123)", DEFAULT_ADMIN["email"])

    # ── Incidents (separate session so suppliers are committed first) ──────
    async with get_db_session() as session:
        from sqlalchemy import select

        now = datetime.utcnow()
        for inc in INCIDENTS:
            result = await session.execute(
                select(Incident).where(Incident.incident_code == inc["incident_code"])
            )
            if result.scalar_one_or_none():
                logger.info("Incident %s already exists, skipping.", inc["incident_code"])
                continue

            days_ago = inc.pop("days_ago", 0)
            sup_id_str = inc.pop("supplier_id")
            session.add(
                Incident(
                    id=str(uuid.uuid4()),
                    supplier_id=supplier_pk_map.get(sup_id_str),
                    supplier_ref=sup_id_str,
                    occurred_at=now - timedelta(days=days_ago),
                    **{k: v for k, v in inc.items()},
                )
            )
            logger.info("Seeded incident: %s", inc["incident_code"])

    logger.info("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
