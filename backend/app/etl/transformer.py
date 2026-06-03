"""Type casting, normalization, and data-aware field derivations.

Key behaviours:
- defect_rate: auto-detected scale (0-1 or 0-100+), normalised before use
- delivery_delay_days: negative = early delivery (valid, LOW risk)
- severity + shipment_status: percentile-based thresholds from actual data distribution
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.etl.schemas import CANONICAL_FIELDS, CANONICAL_TO_PIPELINE

logger = logging.getLogger(__name__)


# ── Shipment status from delay (handles early deliveries) ─────────────────────

def _shipment_status(delay: float) -> str:
    if delay < 0:   return "Early"        # arrived before expected
    if delay == 0:  return "On-Time"
    if delay <= 3:  return "In-Transit"
    if delay <= 7:  return "Delayed"
    return "Critical"


# ── Transformer ───────────────────────────────────────────────────────────────

class Transformer:
    """Applies type casting then derives computed canonical fields."""

    # ── Type casting ──────────────────────────────────────────────────────

    def cast_types(self, df: pd.DataFrame) -> pd.DataFrame:
        for field_name, spec in CANONICAL_FIELDS.items():
            if field_name not in df.columns:
                continue
            if spec["type"] == "float":
                df[field_name] = pd.to_numeric(df[field_name], errors="coerce").fillna(0.0)
            elif spec["type"] == "str":
                df[field_name] = df[field_name].fillna("").astype(str).str.strip()
        return df

    # ── Main derive entry-point ───────────────────────────────────────────

    def derive_fields(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Compute all derived fields. Returns (enriched_df, derived_field_names)."""
        derived: List[str] = []

        # 1. Normalise defect_rate FIRST (downstream steps depend on 0-1 scale)
        df = self._normalize_defect_rate(df, derived)

        # 2. Compute data-aware percentile thresholds from actual distribution
        thresholds = self._compute_thresholds(df)
        logger.info(
            "ETL thresholds — delay p75/p90: %.1f/%.1f  defect p75/p90: %.3f/%.3f  "
            "stock p10/p25: %.0f/%.0f",
            thresholds["delay_p75"], thresholds["delay_p90"],
            thresholds["defect_p75"], thresholds["defect_p90"],
            thresholds["stock_p10"], thresholds["stock_p25"],
        )

        # 3. Derive each field in dependency order
        df = self._derive_supplier_id(df, derived)
        df = self._derive_delivery_delay(df, derived)
        df = self._derive_shipment_status(df, derived)
        df = self._derive_severity(df, derived, thresholds)
        df = self._derive_risk_score(df, derived, thresholds)
        df = self._derive_timestamp(df, derived)
        df = self._derive_incident_code(df, derived)

        return df, derived

    # ── Fix 1: Defect rate normalisation ──────────────────────────────────

    def _normalize_defect_rate(self, df: pd.DataFrame, derived: List[str]) -> pd.DataFrame:
        col = "defect_rate"
        if col not in df.columns:
            return df
        series = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        max_val = series.max()
        if max_val > 1.0:
            # Values are on a percentage or arbitrary scale — normalise to 0-1
            normalised = series / max_val
            df[col] = normalised.round(6)
            logger.info(
                "defect_rate normalised: max was %.4f → divided by %.4f", max_val, max_val
            )
            if col not in derived:
                derived.append(f"{col} (normalised from 0–{max_val:.2f} scale)")
        else:
            df[col] = series
        return df

    # ── Fix 3: Percentile-based threshold computation ─────────────────────

    def _compute_thresholds(self, df: pd.DataFrame) -> Dict[str, float]:
        def _col(name: str, default_val: float) -> pd.Series:
            if name in df.columns:
                return pd.to_numeric(df[name], errors="coerce").fillna(default_val)
            return pd.Series([default_val] * len(df))

        delay     = _col("delivery_delay_days", 0.0)
        defect    = _col("defect_rate", 0.0)
        inventory = _col("inventory_level", 100.0)

        # Clip negative delays for threshold computation only
        # (negatives are valid early deliveries but shouldn't skew p75/p90)
        delay_pos = delay.clip(lower=0)

        return {
            "delay_p50":  float(delay_pos.quantile(0.50)),
            "delay_p75":  float(delay_pos.quantile(0.75)),
            "delay_p90":  float(delay_pos.quantile(0.90)),
            "defect_p50": float(defect.quantile(0.50)),
            "defect_p75": float(defect.quantile(0.75)),
            "defect_p90": float(defect.quantile(0.90)),
            "stock_p10":  float(inventory.quantile(0.10)),
            "stock_p25":  float(inventory.quantile(0.25)),
            "stock_p50":  float(inventory.quantile(0.50)),
        }

    # ── Individual derivation helpers ─────────────────────────────────────

    def _derive_supplier_id(self, df: pd.DataFrame, derived: List[str]) -> pd.DataFrame:
        col = "supplier_id"
        if col not in df.columns or df[col].eq("").all():
            if "supplier_name" in df.columns and not df["supplier_name"].eq("").all():
                df[col] = (
                    df["supplier_name"]
                    .str.lower()
                    .str.replace(r"[^a-z0-9]+", "-", regex=True)
                    .str.strip("-")
                )
                derived.append(col)
            else:
                df[col] = [f"SUP-{i+1:04d}" for i in range(len(df))]
                derived.append(col)
        return df

    def _derive_delivery_delay(self, df: pd.DataFrame, derived: List[str]) -> pd.DataFrame:
        col = "delivery_delay_days"
        if col not in df.columns or (df[col] == 0).all():
            if "lead_time_days" in df.columns:
                shipping_est = df["lead_time_days"] * 0.80
                # Keep negative (early) deliveries — do NOT clip to 0
                df[col] = (df["lead_time_days"] - shipping_est).round(2)
                derived.append(col)
        return df

    def _derive_shipment_status(self, df: pd.DataFrame, derived: List[str]) -> pd.DataFrame:
        """Fix 2: Negative delays → 'Early' (valid, not an error)."""
        col = "shipment_status"
        if col not in df.columns or df[col].eq("").all():
            if "delivery_delay_days" in df.columns:
                df[col] = df["delivery_delay_days"].apply(
                    lambda d: _shipment_status(float(d) if pd.notna(d) else 0)
                )
                derived.append(col)
            else:
                df[col] = "On-Time"
        return df

    def _derive_severity(
        self, df: pd.DataFrame, derived: List[str], thresholds: Dict[str, float]
    ) -> pd.DataFrame:
        """Fix 3: Percentile-based severity — adapts to any dataset distribution."""
        col = "severity"
        t = thresholds

        delay     = pd.to_numeric(df.get("delivery_delay_days", pd.Series([0.0]*len(df))), errors="coerce").fillna(0.0)
        defect    = pd.to_numeric(df.get("defect_rate",         pd.Series([0.0]*len(df))), errors="coerce").fillna(0.0)
        inventory = pd.to_numeric(df.get("inventory_level",     pd.Series([100.0]*len(df))), errors="coerce").fillna(100.0)

        def _sev(d: float, def_: float, inv: float) -> str:
            # Fix 2: early delivery is always LOW risk
            if d < 0:
                return "low"
            is_critical = d > t["delay_p90"] or def_ > t["defect_p90"] or inv < t["stock_p10"]
            is_high     = d > t["delay_p75"] or def_ > t["defect_p75"] or inv < t["stock_p25"]
            is_medium   = d > t["delay_p50"] or def_ > t["defect_p50"] or inv < t["stock_p50"]
            if is_critical: return "critical"
            if is_high:     return "high"
            if is_medium:   return "medium"
            return "low"

        df[col] = [_sev(d, def_, inv) for d, def_, inv in zip(delay, defect, inventory)]
        derived.append(col)
        return df

    def _derive_risk_score(
        self, df: pd.DataFrame, derived: List[str], thresholds: Dict[str, float]
    ) -> pd.DataFrame:
        """Risk score 0-100 using normalised metrics relative to data distribution."""
        col = "risk_score"
        t = thresholds

        delay     = pd.to_numeric(df.get("delivery_delay_days", pd.Series([0.0]*len(df))), errors="coerce").fillna(0.0)
        defect    = pd.to_numeric(df.get("defect_rate",         pd.Series([0.0]*len(df))), errors="coerce").fillna(0.0)
        inventory = pd.to_numeric(df.get("inventory_level",     pd.Series([100.0]*len(df))), errors="coerce").fillna(100.0)
        tcost     = pd.to_numeric(df.get("transportation_cost", pd.Series([0.0]*len(df))), errors="coerce").fillna(0.0)
        avg_cost  = float(tcost.mean()) if tcost.max() > 0 else 1.0
        max_delay = max(float(t["delay_p90"]) * 1.5, 1.0)
        max_inv   = max(float(inventory.max()), 1.0)

        def _score(d: float, def_: float, inv: float, tc: float) -> float:
            # Negative delay = below-average risk (cap contribution at 0)
            delay_score   = max(0.0, min(d / max_delay, 1.0))
            inv_score     = 1.0 - min(inv / max_inv, 1.0)
            defect_score  = min(def_ / max(float(t["defect_p90"]) * 1.5, 0.001), 1.0)
            cost_ratio    = tc / avg_cost if avg_cost > 0 else 1.0
            cost_score    = min(max(cost_ratio - 1.0, 0.0) / 2.0, 1.0)
            return round(
                (delay_score * 0.35 + inv_score * 0.25 + defect_score * 0.20 + cost_score * 0.20) * 100,
                2,
            )

        df[col] = [_score(d, def_, inv, tc) for d, def_, inv, tc in zip(delay, defect, inventory, tcost)]
        derived.append(col)
        return df

    def _derive_timestamp(self, df: pd.DataFrame, derived: List[str]) -> pd.DataFrame:
        """Fix 6: Spread timestamps over last 30 days so alerts show natural age."""
        col = "timestamp"
        now = datetime.now(timezone.utc)
        n   = len(df)

        if col not in df.columns or df[col].eq("").all():
            # Distribute evenly from 30 days ago to now so history looks natural
            timestamps = [
                (now - timedelta(days=int(i / max(n - 1, 1) * 30),
                                 hours=i % 24)).strftime("%Y-%m-%dT%H:%M:%S")
                for i in range(n)
            ]
            df[col] = timestamps
            derived.append(col)
        else:
            parsed = pd.to_datetime(df[col], errors="coerce")
            df[col] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S").fillna(now.strftime("%Y-%m-%dT%H:%M:%S"))
        return df

    def _derive_incident_code(self, df: pd.DataFrame, derived: List[str]) -> pd.DataFrame:
        col = "sku"
        if col not in df.columns or df[col].eq("").all():
            df[col] = [f"INC-ETL-{i+1:05d}" for i in range(len(df))]
            derived.append("sku")
        return df

    # ── Distribution helpers (for summary card) ───────────────────────────

    @staticmethod
    def compute_distributions(df: pd.DataFrame) -> Dict[str, Dict[str, int]]:
        """Return severity and shipment_status breakdowns for the summary card."""
        result: Dict[str, Dict[str, int]] = {}
        for col in ("severity", "shipment_status"):
            if col in df.columns:
                result[col] = df[col].value_counts().to_dict()
        return result

    # ── Canonical → pipeline format ───────────────────────────────────────

    def to_pipeline_format(self, df: pd.DataFrame) -> pd.DataFrame:
        renamed = df.rename(columns=CANONICAL_TO_PIPELINE)

        # ── Fixes 4 & 5: specific title, description, and data-driven category ──

        def _primary_reason(row: Any) -> str:
            """Return the most impactful single reason for this record."""
            defect  = float(row.get("DefectRate", 0) or 0)
            inv     = float(row.get("InventoryLevel", 0) or 0)
            demand  = float(row.get("DemandForecast", 1) or 1)
            delay   = float(row.get("DeliveryDelayDays", 0) or 0)
            lead    = float(row.get("LeadTimeDays", 0) or 0)
            insp    = str(row.get("InspectionStatus", "")).lower()
            coverage = inv / demand if demand > 0 else 1.0

            if defect > 0.05 or "fail" in insp:
                return f"Defect rate {defect*100:.1f}% critical"
            if coverage < 0.3:
                return f"Stock level {inv:.0f} units, stockout imminent"
            if delay > 7:
                return f"Delivery delay {delay:.0f} days, critical"
            if lead > 20:
                return f"Lead time {lead:.0f} days, severe delay"
            if delay > 3:
                return f"Delivery delay {delay:.0f} days"
            if coverage < 0.5:
                return f"Low stock {inv:.0f}/{demand:.0f} units"
            return f"Supply chain risk detected"

        def _build_title(row: Any) -> str:
            sku      = str(row.get("IncidentCode", "SKU?"))
            supplier = str(row.get("SupplierName") or row.get("SupplierID") or "Unknown")
            location = str(row.get("WarehouseLocation") or "")
            reason   = _primary_reason(row)
            loc_str  = f", {location}" if location and location != "N/A" else ""
            return f"{sku}: {reason} — {supplier}{loc_str}"

        def _build_desc(row: Any) -> str:
            parts = []
            defect = float(row.get("DefectRate", 0) or 0)
            inv    = float(row.get("InventoryLevel", 0) or 0)
            demand = float(row.get("DemandForecast", 1) or 1)
            delay  = float(row.get("DeliveryDelayDays", 0) or 0)
            lead   = float(row.get("LeadTimeDays", 0) or 0)
            cost   = float(row.get("TransportationCost", 0) or 0)

            if defect > 0:
                parts.append(f"Defect rate: {defect*100:.2f}%.")
            if demand > 0:
                parts.append(f"Stock: {inv:.0f} units vs {demand:.0f} forecast (ratio: {inv/demand:.2f}).")
            if delay != 0:
                if delay < 0:
                    parts.append(f"Early delivery: {abs(delay):.1f} days ahead.")
                else:
                    parts.append(f"Delay: {delay:.1f} days.")
            if lead > 0:
                parts.append(f"Lead time: {lead:.0f} days.")
            if cost > 0:
                parts.append(f"Transport cost: ${cost:,.0f}.")
            return " ".join(parts) or "Automated ETL record."

        def _derive_category(row: Any) -> str:
            """Fix 5: category reflects the actual primary trigger."""
            defect     = float(row.get("DefectRate", 0) or 0)
            inv        = float(row.get("InventoryLevel", 0) or 0)
            demand     = float(row.get("DemandForecast", 1) or 1)
            delay      = float(row.get("DeliveryDelayDays", 0) or 0)
            insp       = str(row.get("InspectionStatus", "")).lower()
            coverage   = inv / demand if demand > 0 else 1.0

            quality_trigger   = defect > 0.05 or "fail" in insp
            inventory_trigger = coverage < 0.5
            shipment_trigger  = delay > 5

            count = sum([quality_trigger, inventory_trigger, shipment_trigger])
            if count >= 2:
                return "supplier"   # multi-risk → supplier (enum value)
            if quality_trigger:
                return "supplier"   # quality issues tracked as supplier problems
            if inventory_trigger:
                return "inventory"
            if shipment_trigger:
                return "shipment"
            return "supplier"

        if "Title" not in renamed.columns:
            renamed["Title"] = renamed.apply(_build_title, axis=1)
        if "Description" not in renamed.columns:
            renamed["Description"] = renamed.apply(_build_desc, axis=1)

        # Always recompute category from data (don't accept default "supplier" for all)
        renamed["IncidentCategory"] = renamed.apply(_derive_category, axis=1)

        if "ResolutionStatus" not in renamed.columns:
            renamed["ResolutionStatus"] = "open"
        if "Region" not in renamed.columns:
            renamed["Region"] = ""

        return renamed
