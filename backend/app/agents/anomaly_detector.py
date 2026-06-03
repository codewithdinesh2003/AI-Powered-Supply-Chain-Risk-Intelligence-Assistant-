"""Statistical anomaly detection — pure numpy/pandas, no ML library required.

Detects four types of anomalies:
  statistical_outlier  — z-score > 2.5 std on key numeric columns
  stockout_risk        — inventory < 10% of dataset average
  trend                — monotonically increasing delivery delays over last 10 rows
  defect_spike         — supplier defect rate > 2× dataset average
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class AnomalyEvent:
    anomaly_type: str       # statistical_outlier | stockout_risk | trend | defect_spike
    field: str
    value: float
    supplier_name: str
    sku: str
    location: str
    severity: str           # critical | high | medium
    description: str
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "anomaly_type": self.anomaly_type,
            "field":        self.field,
            "value":        self.value,
            "supplier_name":self.supplier_name,
            "sku":          self.sku,
            "location":     self.location,
            "severity":     self.severity,
            "description":  self.description,
            "detected_at":  self.detected_at,
        }


class AnomalyDetector:
    """Run z-score, stockout, trend, and defect-spike detection on canonical DataFrame."""

    def detect(self, df: pd.DataFrame) -> List[AnomalyEvent]:
        anomalies: List[AnomalyEvent] = []
        anomalies.extend(self._zscore_anomalies(df))
        anomalies.extend(self._stockout_risk(df))
        anomalies.extend(self._delay_trend(df))
        anomalies.extend(self._defect_spike(df))
        logger.info("Anomaly detection complete: %d events found.", len(anomalies))
        return anomalies

    # ── Z-score outliers ──────────────────────────────────────────────────

    def _zscore_anomalies(self, df: pd.DataFrame) -> List[AnomalyEvent]:
        results = []
        for col in ("delivery_delay_days", "transportation_cost", "defect_rate"):
            if col not in df.columns:
                continue
            series = pd.to_numeric(df[col], errors="coerce").fillna(0)
            mean, std = float(series.mean()), float(series.std())
            if std == 0:
                continue
            z_scores = (series - mean) / std
            outlier_mask = z_scores.abs() > 2.5
            for idx in df[outlier_mask].index:
                row = df.loc[idx]
                z   = abs(float(z_scores[idx]))
                sev = "critical" if z > 3.5 else "high"
                results.append(AnomalyEvent(
                    anomaly_type="statistical_outlier",
                    field=col,
                    value=round(float(row[col]), 4),
                    supplier_name=str(row.get("supplier_name", "Unknown")),
                    sku=str(row.get("sku", "Unknown")),
                    location=str(row.get("warehouse_location", "")),
                    severity=sev,
                    description=(
                        f"{col.replace('_', ' ').title()} is {z:.1f}σ above normal "
                        f"(value: {float(row[col]):.2f}, avg: {mean:.2f})"
                    ),
                ))
        return results

    # ── Stockout risk ─────────────────────────────────────────────────────

    def _stockout_risk(self, df: pd.DataFrame) -> List[AnomalyEvent]:
        if "inventory_level" not in df.columns:
            return []
        inv = pd.to_numeric(df["inventory_level"], errors="coerce").fillna(0)
        threshold = max(float(inv.mean()) * 0.10, 5.0)
        results = []
        for idx in df[inv < threshold].index:
            row    = df.loc[idx]
            stock  = float(row.get("inventory_level", 0))
            demand = float(row.get("demand_forecast", 1) or 1)
            days   = round(stock / demand, 1) if demand > 0 else 0
            results.append(AnomalyEvent(
                anomaly_type="stockout_risk",
                field="inventory_level",
                value=stock,
                supplier_name=str(row.get("supplier_name", "Unknown")),
                sku=str(row.get("sku", "Unknown")),
                location=str(row.get("warehouse_location", "")),
                severity="critical" if stock <= 2 else "high",
                description=(
                    f"Stock level {stock:.0f} units — estimated {days} days until stockout "
                    f"(demand forecast: {demand:.0f} units)"
                ),
            ))
        return results

    # ── Delay trend ───────────────────────────────────────────────────────

    def _delay_trend(self, df: pd.DataFrame) -> List[AnomalyEvent]:
        if "delivery_delay_days" not in df.columns or len(df) < 10:
            return []
        recent = pd.to_numeric(df["delivery_delay_days"].tail(10), errors="coerce").fillna(0).clip(lower=0)
        if recent.is_monotonic_increasing and recent.max() > recent.min():
            return [AnomalyEvent(
                anomaly_type="trend",
                field="delivery_delay_days",
                value=float(recent.max()),
                supplier_name="Multiple",
                sku="Multiple",
                location="Multiple",
                severity="high",
                description=(
                    f"Delivery delays consistently increasing over last 10 records "
                    f"(min: {recent.min():.1f} → max: {recent.max():.1f} days)"
                ),
            )]
        return []

    # ── Defect spike ──────────────────────────────────────────────────────

    def _defect_spike(self, df: pd.DataFrame) -> List[AnomalyEvent]:
        if "defect_rate" not in df.columns or "supplier_name" not in df.columns:
            return []
        defect = pd.to_numeric(df["defect_rate"], errors="coerce").fillna(0)
        avg    = float(defect.mean())
        if avg == 0:
            return []
        df_copy   = df.copy()
        df_copy["_d"] = defect
        grouped   = df_copy.groupby("supplier_name")["_d"].mean()
        results   = []
        for sup_name, sup_avg in grouped.items():
            if sup_avg > avg * 2.0:
                results.append(AnomalyEvent(
                    anomaly_type="defect_spike",
                    field="defect_rate",
                    value=round(float(sup_avg), 4),
                    supplier_name=str(sup_name),
                    sku="Multiple",
                    location="Multiple",
                    severity="critical" if sup_avg > avg * 3.0 else "high",
                    description=(
                        f"{sup_name} defect rate {sup_avg*100:.1f}% is "
                        f"{sup_avg/avg:.1f}× the dataset average ({avg*100:.1f}%)"
                    ),
                ))
        return results
