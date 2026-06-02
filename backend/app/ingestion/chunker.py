from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd


@dataclass
class DocumentChunk:
    chunk_id: str
    text: str
    metadata: dict
    supplier_ref: str
    chunk_type: str  # "record" | "supplier_summary"


# ── Severity helpers ─────────────────────────────────────────────────────────

def _calc_severity(delay_days: float, inventory: float, demand: float) -> str:
    coverage = inventory / demand if demand > 0 else 1.0
    if delay_days > 14 or coverage < 0.20:
        return "critical"
    if delay_days > 7 or coverage < 0.50:
        return "high"
    if delay_days > 3 or coverage < 0.70:
        return "medium"
    return "low"


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val) if pd.notna(val) else default
    except (TypeError, ValueError):
        return default


def _safe_str(val, default: str = "N/A") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return str(val).strip() or default


# ── Main chunker ─────────────────────────────────────────────────────────────

class SupplyChainChunker:
    """Converts a supply-chain CSV DataFrame into rich text DocumentChunks.

    Two chunk types:
    - ``record``           — one chunk per CSV row, full event detail
    - ``supplier_summary`` — one chunk per unique supplier, aggregated stats
    """

    def chunk_dataframe(self, df: pd.DataFrame) -> List[DocumentChunk]:
        chunks: List[DocumentChunk] = []

        for idx, row in df.iterrows():
            chunks.append(self._record_chunk(row, idx))

        for supplier_id, group in df.groupby("SupplierID", sort=False):
            chunks.append(self._supplier_summary_chunk(str(supplier_id), group))

        return chunks

    # ── Per-record chunk ──────────────────────────────────────────────────

    def _record_chunk(self, row: pd.Series, idx: int) -> DocumentChunk:
        delay = _safe_float(row.get("DeliveryDelayDays"))
        inventory = _safe_float(row.get("InventoryLevel"), 100.0)
        demand = _safe_float(row.get("DemandForecast"), 100.0)
        severity = _calc_severity(delay, inventory, demand)
        coverage = inventory / demand if demand > 0 else 1.0

        supplier_id = _safe_str(row.get("SupplierID"))
        incident_code = _safe_str(row.get("IncidentCode"), f"INC-{idx:05d}")

        text = (
            f"SUPPLY CHAIN INCIDENT REPORT\n"
            f"Incident Code: {incident_code}\n"
            f"Supplier: {_safe_str(row.get('SupplierName'))} (ID: {supplier_id})\n"
            f"Region: {_safe_str(row.get('Region'))} | "
            f"Category: {_safe_str(row.get('SupplierCategory'))}\n"
            f"Reliability Score: {_safe_float(row.get('ReliabilityScore')):.1f}/100\n"
            f"\n"
            f"Logistics:\n"
            f"  Warehouse Location: {_safe_str(row.get('WarehouseLocation'))}\n"
            f"  Shipment Status: {_safe_str(row.get('ShipmentStatus'))}\n"
            f"  Delivery Delay: {delay:.1f} days\n"
            f"  Transportation Cost: ${_safe_float(row.get('TransportationCost')):,.2f}\n"
            f"\n"
            f"Inventory:\n"
            f"  Current Level: {inventory:.0f} units\n"
            f"  Demand Forecast: {demand:.0f} units\n"
            f"  Coverage Ratio: {coverage:.2f} "
            f"({'STOCKOUT RISK' if coverage < 0.5 else 'ADEQUATE'})\n"
            f"\n"
            f"Incident:\n"
            f"  Title: {_safe_str(row.get('Title'))}\n"
            f"  Description: {_safe_str(row.get('Description'))}\n"
            f"  Severity: {severity.upper()}\n"
            f"  Category: {_safe_str(row.get('IncidentCategory'))}\n"
            f"  Date: {_safe_str(row.get('OccurredAt'))}\n"
            f"  Resolution: {_safe_str(row.get('ResolutionStatus'), 'open')}\n"
        )

        metadata: dict = {
            "supplier_id": supplier_id,
            "supplier_name": _safe_str(row.get("SupplierName")),
            "region": _safe_str(row.get("Region")),
            "supplier_category": _safe_str(row.get("SupplierCategory")),
            "severity": severity,
            "incident_category": _safe_str(row.get("IncidentCategory"), "supplier"),
            "warehouse_location": _safe_str(row.get("WarehouseLocation")),
            "shipment_status": _safe_str(row.get("ShipmentStatus")),
            "delivery_delay_days": round(delay, 2),
            "transportation_cost": round(_safe_float(row.get("TransportationCost")), 2),
            "inventory_level": round(inventory, 2),
            "demand_forecast": round(demand, 2),
            "coverage_ratio": round(coverage, 4),
            "resolution_status": _safe_str(row.get("ResolutionStatus"), "open"),
            "incident_code": incident_code,
            "chunk_type": "record",
        }

        # Store date components for range-filter queries
        raw_date = row.get("OccurredAt")
        if raw_date is not None and pd.notna(raw_date):
            try:
                ts = pd.to_datetime(raw_date)
                metadata["occurred_at"] = ts.isoformat()
                metadata["year"] = int(ts.year)
                metadata["month"] = int(ts.month)
            except Exception:
                pass

        return DocumentChunk(
            chunk_id=f"record_{incident_code}_{supplier_id}",
            text=text,
            metadata=metadata,
            supplier_ref=supplier_id,
            chunk_type="record",
        )

    # ── Supplier summary chunk ─────────────────────────────────────────────

    def _supplier_summary_chunk(
        self, supplier_id: str, group: pd.DataFrame
    ) -> DocumentChunk:
        name = _safe_str(group["SupplierName"].iloc[0] if "SupplierName" in group.columns else None)
        region = _safe_str(group["Region"].iloc[0] if "Region" in group.columns else None)
        category = _safe_str(group["SupplierCategory"].iloc[0] if "SupplierCategory" in group.columns else None)

        delays = [_safe_float(v) for v in group.get("DeliveryDelayDays", [])]
        inventories = [_safe_float(v, 100.0) for v in group.get("InventoryLevel", [])]
        demands = [_safe_float(v, 100.0) for v in group.get("DemandForecast", [])]
        reliabilities = [_safe_float(v) for v in group.get("ReliabilityScore", [])]

        avg_delay = sum(delays) / len(delays) if delays else 0.0
        avg_reliability = sum(reliabilities) / len(reliabilities) if reliabilities else 0.0

        severities = [
            _calc_severity(d, i, dm)
            for d, i, dm in zip(delays, inventories, demands)
        ]
        critical_count = severities.count("critical")
        high_count = severities.count("high")
        total = len(group)

        # Recent incidents (up to 5)
        recent_lines = []
        for _, row in group.head(5).iterrows():
            sev = _calc_severity(
                _safe_float(row.get("DeliveryDelayDays")),
                _safe_float(row.get("InventoryLevel"), 100.0),
                _safe_float(row.get("DemandForecast"), 100.0),
            )
            recent_lines.append(
                f"  [{_safe_str(row.get('OccurredAt'))}] "
                f"{_safe_str(row.get('Title'))} ({sev.upper()})"
            )

        if critical_count >= 3:
            risk_label = "CRITICAL SUPPLIER — Multiple critical incidents detected"
            overall_severity = "critical"
        elif high_count >= 3 or avg_delay > 10:
            risk_label = "HIGH RISK SUPPLIER — Frequent high-severity delays"
            overall_severity = "high"
        elif avg_delay > 3:
            risk_label = "MEDIUM RISK SUPPLIER — Some delivery issues"
            overall_severity = "medium"
        else:
            risk_label = "LOW RISK SUPPLIER — Generally reliable performance"
            overall_severity = "low"

        text = (
            f"SUPPLIER PERFORMANCE SUMMARY\n"
            f"Supplier: {name} (ID: {supplier_id})\n"
            f"Region: {region} | Category: {category}\n"
            f"Total Incidents on Record: {total}\n"
            f"\n"
            f"Performance Metrics:\n"
            f"  Average Reliability Score: {avg_reliability:.1f}/100\n"
            f"  Average Delivery Delay: {avg_delay:.1f} days\n"
            f"  Critical Incidents: {critical_count}\n"
            f"  High-Severity Incidents: {high_count}\n"
            f"\n"
            f"Recent Incident History:\n"
            + "\n".join(recent_lines) + "\n"
            f"\n"
            f"Risk Assessment: {risk_label}\n"
        )

        metadata: dict = {
            "supplier_id": supplier_id,
            "supplier_name": name,
            "region": region,
            "supplier_category": category,
            "avg_delay_days": round(avg_delay, 2),
            "avg_reliability_score": round(avg_reliability, 2),
            "total_incidents": int(total),
            "critical_incidents": int(critical_count),
            "high_incidents": int(high_count),
            "severity": overall_severity,
            "chunk_type": "supplier_summary",
        }

        return DocumentChunk(
            chunk_id=f"supplier_summary_{supplier_id}",
            text=text,
            metadata=metadata,
            supplier_ref=supplier_id,
            chunk_type="supplier_summary",
        )
