#!/usr/bin/env python
"""Generate a realistic supply_chain_data.csv for development / demo.

Usage:
    python data/generate_sample_data.py               # → data/supply_chain_data.csv
    python data/generate_sample_data.py --rows 1000   # larger dataset
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

# ── Reference data ────────────────────────────────────────────────────────────

SUPPLIERS = [
    ("SUP-001", "GlobalTech Components",    "Asia-Pacific",   "Electronics"),
    ("SUP-002", "Pacific Rim Manufacturing","Asia-Pacific",   "Raw Materials"),
    ("SUP-003", "EuroLogistics Partners",   "Europe",         "Logistics"),
    ("SUP-004", "NorAm Supply Chain",       "North America",  "Packaging"),
    ("SUP-005", "Gulf Region Distributors", "Middle East",    "Manufacturing"),
    ("SUP-006", "Andean Resources Ltd",     "South America",  "Raw Materials"),
    ("SUP-007", "Southeast Asia Textiles",  "Asia-Pacific",   "Manufacturing"),
    ("SUP-008", "Nordic Cold Chain",        "Europe",         "Logistics"),
    ("SUP-009", "Midwest Components Inc",   "North America",  "Electronics"),
    ("SUP-010", "Bay Area Tech Supplies",   "North America",  "Electronics"),
]

# (supplier_id → base_reliability, base_delay_mean, delay_std)
SUPPLIER_PROFILES = {
    "SUP-001": (72, 4.5,  3.0),
    "SUP-002": (45, 12.3, 6.0),
    "SUP-003": (88, 1.2,  1.0),
    "SUP-004": (65, 6.7,  4.0),
    "SUP-005": (58, 9.1,  5.0),
    "SUP-006": (79, 3.4,  2.5),
    "SUP-007": (61, 7.8,  5.5),
    "SUP-008": (92, 0.8,  0.5),
    "SUP-009": (70, 5.0,  3.5),
    "SUP-010": (83, 2.1,  1.5),
}

WAREHOUSES = [
    "Shanghai, China", "Singapore", "Los Angeles, USA", "Rotterdam, Netherlands",
    "Dubai, UAE", "São Paulo, Brazil", "Chicago, USA", "Frankfurt, Germany",
    "Mumbai, India", "Tokyo, Japan", "Sydney, Australia", "Houston, USA",
]

SHIPMENT_STATUSES = ["On-Time", "Delayed", "Critical", "In-Transit", "Customs-Hold"]

INCIDENT_CATEGORIES = ["supplier", "shipment", "inventory", "demand"]

INCIDENT_TEMPLATES = [
    # (title_template, description_template, category_hint)
    ("{supplier} delivery delayed by customs clearance",
     "Shipment from {supplier} held at {warehouse} customs for {delay:.0f} days due to documentation issues.",
     "shipment"),
    ("Low inventory alert — {supplier} components",
     "Stock levels for {category} components from {supplier} have dropped below reorder point. "
     "Current: {inventory:.0f} units vs demand forecast: {demand:.0f} units.",
     "inventory"),
    ("{supplier} reliability score degradation",
     "Supplier {supplier} has shown a pattern of late deliveries over the past 30 days, "
     "averaging {delay:.1f} days behind schedule.",
     "supplier"),
    ("Transportation cost spike on {region} routes",
     "Freight costs from {region} increased by {pct:.0f}% due to fuel surcharges and carrier capacity constraints.",
     "shipment"),
    ("Demand surge exceeds {supplier} capacity",
     "Q-on-Q demand has increased by {pct:.0f}%, exceeding current supply agreements with {supplier}.",
     "demand"),
    ("Port congestion affecting {supplier} shipments",
     "Congestion at {warehouse} port is causing {delay:.0f}-day delays for all {supplier} shipments.",
     "shipment"),
    ("{supplier} quality control hold",
     "Batch from {supplier} placed on quality hold pending inspection. "
     "{inventory:.0f} units temporarily unavailable.",
     "supplier"),
    ("Weather-related disruption — {region}",
     "Severe weather event in {region} has disrupted logistics for {supplier}, "
     "causing estimated {delay:.0f}-day delay.",
     "shipment"),
    ("Stockout risk for {category} components",
     "At current consumption rate, {category} component stock will reach zero in "
     "{days:.0f} days without restocking.",
     "inventory"),
    ("Geopolitical risk — {region} trade route",
     "New regulatory requirements in {region} affecting imports from {supplier}. "
     "Compliance timeline: {days:.0f} days.",
     "supplier"),
]

RESOLUTION_STATUSES = ["open", "open", "open", "in_progress", "in_progress", "resolved", "closed"]


def _calc_severity(delay: float, inventory: float, demand: float) -> str:
    coverage = inventory / demand if demand > 0 else 1.0
    if delay > 14 or coverage < 0.20:
        return "critical"
    if delay > 7 or coverage < 0.50:
        return "high"
    if delay > 3 or coverage < 0.70:
        return "medium"
    return "low"


def _calc_impact(severity: str) -> float:
    base = {"critical": 8.5, "high": 6.5, "medium": 4.0, "low": 2.0}[severity]
    return round(base + random.uniform(-1.0, 1.0), 2)


def generate(n_rows: int = 500) -> pd.DataFrame:
    rows = []
    start_date = datetime.now() - timedelta(days=365)

    for i in range(n_rows):
        sup_id, sup_name, region, category = random.choice(SUPPLIERS)
        reliability_base, delay_mean, delay_std = SUPPLIER_PROFILES[sup_id]

        reliability = max(10.0, min(100.0, reliability_base + random.gauss(0, 5)))
        delay = max(0.0, random.gauss(delay_mean, delay_std))
        transport_cost = random.uniform(2000, 55000)
        inventory = random.uniform(50, 5000)
        demand = random.uniform(100, 4000)
        occurred_at = start_date + timedelta(days=random.randint(0, 365))
        warehouse = random.choice(WAREHOUSES)
        pct = random.uniform(10, 65)
        days = random.uniform(3, 30)

        if delay > 14:
            status = "Critical"
        elif delay > 5:
            status = random.choice(["Delayed", "In-Transit"])
        elif random.random() < 0.1:
            status = "Customs-Hold"
        else:
            status = "On-Time"

        tmpl = random.choice(INCIDENT_TEMPLATES)
        title = tmpl[0].format(
            supplier=sup_name, region=region, category=category,
            warehouse=warehouse, delay=delay, inventory=inventory,
            demand=demand, pct=pct, days=days,
        )
        description = tmpl[1].format(
            supplier=sup_name, region=region, category=category,
            warehouse=warehouse, delay=delay, inventory=inventory,
            demand=demand, pct=pct, days=days,
        )
        inc_category = tmpl[2]

        severity = _calc_severity(delay, inventory, demand)

        rows.append({
            "IncidentCode": f"INC-{i+1:05d}",
            "SupplierID": sup_id,
            "SupplierName": sup_name,
            "Region": region,
            "SupplierCategory": category,
            "ReliabilityScore": round(reliability, 2),
            "WarehouseLocation": warehouse,
            "ShipmentStatus": status,
            "DeliveryDelayDays": round(delay, 2),
            "TransportationCost": round(transport_cost, 2),
            "InventoryLevel": round(inventory, 2),
            "DemandForecast": round(demand, 2),
            "IncidentCategory": inc_category,
            "Title": title,
            "Description": description,
            "Severity": severity,
            "ImpactScore": _calc_impact(severity),
            "OccurredAt": occurred_at.strftime("%Y-%m-%d"),
            "ResolutionStatus": random.choice(RESOLUTION_STATUSES),
        })

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample supply chain CSV.")
    parser.add_argument("--rows", type=int, default=500, help="Number of rows to generate.")
    parser.add_argument("--out", default=str(Path(__file__).parent / "supply_chain_data.csv"))
    args = parser.parse_args()

    print(f"Generating {args.rows} rows...")
    df = generate(args.rows)
    df.to_csv(args.out, index=False)
    print(f"Saved to {args.out}")
    print(f"\nSample severity distribution:\n{df['Severity'].value_counts().to_string()}")
    print(f"\nShipment status distribution:\n{df['ShipmentStatus'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
