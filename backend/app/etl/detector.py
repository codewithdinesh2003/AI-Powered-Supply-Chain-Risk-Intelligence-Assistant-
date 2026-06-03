"""Rule-based column mapper — zero LLM involvement.

Three-layer detection:
  Layer 1 — Exact alias lookup   (O(1), instant, highest confidence)
  Layer 2 — Fuzzy matching       (rapidfuzz.fuzz.ratio, catches typos / abbreviations)
  Layer 3 — Data-type inference  (value-pattern recognition, used to break ties)

No API calls, no external services — fully deterministic and offline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.etl.schemas import (
    CANONICAL_FIELDS,
    KNOWN_ALIASES,
    _ALIAS_LOOKUP,
    _norm,
)

logger = logging.getLogger(__name__)

# Confidence thresholds
_HIGH   = 0.85   # auto-map, no user confirmation required
_MEDIUM = 0.60   # suggest, user should confirm
# Below _MEDIUM → UNKNOWN, user must manually assign


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class FieldMapping:
    source_column: Optional[str]
    transform: str                    # direct | derive | divide_by_100 | ...
    derive_formula: Optional[str]
    confidence: float                 # 0.0 – 1.0
    match_layer: str = "none"         # "exact" | "fuzzy" | "dtype" | "derive" | "none"


@dataclass
class DetectionResult:
    mappings: Dict[str, FieldMapping]
    missing_fields: List[str]
    notes: str
    source_columns: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mappings": {
                k: {
                    "source_column":  v.source_column,
                    "transform":      v.transform,
                    "derive_formula": v.derive_formula,
                    "confidence":     v.confidence,
                    "match_layer":    v.match_layer,
                }
                for k, v in self.mappings.items()
            },
            "missing_fields": self.missing_fields,
            "notes":          self.notes,
            "source_columns": self.source_columns,
        }


# ── Layer 1: Exact alias lookup ───────────────────────────────────────────────

def _layer1(col: str) -> Optional[Tuple[str, float]]:
    """O(1) exact lookup using pre-built _ALIAS_LOOKUP dict.

    Returns (canonical_field, confidence) or None.
    """
    canonical = _ALIAS_LOOKUP.get(_norm(col))
    if canonical:
        return canonical, 0.95
    return None


# ── Layer 2: Fuzzy matching ───────────────────────────────────────────────────

def _layer2(col: str) -> Optional[Tuple[str, float]]:
    """rapidfuzz ratio against every known alias.

    Scores ≥ 85 → HIGH confidence (auto-map)
    Scores 60–84 → MEDIUM confidence (user confirms)
    Scores < 60  → None (user must manually assign)
    """
    from rapidfuzz import fuzz

    col_norm = _norm(col)
    best_canonical = None
    best_score     = 0

    for canonical, aliases in KNOWN_ALIASES.items():
        for alias in aliases:
            score = fuzz.ratio(col_norm, _norm(alias))
            if score > best_score:
                best_score     = score
                best_canonical = canonical

    confidence = best_score / 100.0

    if confidence >= _HIGH:
        return best_canonical, confidence
    if confidence >= _MEDIUM:
        return best_canonical, confidence
    return None


# ── Layer 3: Data-type / value-pattern inference ──────────────────────────────

# Value-set patterns for categorical fields
_TRANSPORT_MODES    = {"road", "air", "rail", "sea", "truck", "ship", "plane", "train", "air freight", "ocean"}
_INSPECTION_VALS    = {"pass", "fail", "pending", "passed", "failed", "approved", "rejected"}
_SHIPMENT_STATUSES  = {"on-time", "delayed", "critical", "in-transit", "on_time", "customs-hold", "pending", "cancelled"}


def _layer3(col: str, series: pd.Series) -> Optional[Tuple[str, float, str]]:
    """Infer canonical field from value patterns.

    Returns (canonical_field, confidence, suggested_transform) or None.
    """
    str_vals = series.dropna().astype(str).str.lower().str.strip()
    numeric  = pd.to_numeric(series, errors="coerce")
    non_null_num = numeric.dropna()

    # ── Categorical value-set matching (high confidence) ──────────────────

    if len(str_vals) >= 3:
        unique_lower = set(str_vals.unique()[:50])  # sample unique values

        if unique_lower.issubset(_TRANSPORT_MODES) and len(unique_lower) >= 2:
            return "transportation_mode", 0.92, "direct"

        if unique_lower.issubset(_INSPECTION_VALS) and len(unique_lower) >= 2:
            return "inspection_status", 0.92, "direct"

        if unique_lower.issubset(_SHIPMENT_STATUSES) and len(unique_lower) >= 2:
            return "shipment_status", 0.90, "direct"

    # ── Numeric range patterns ─────────────────────────────────────────────

    if len(non_null_num) >= 3:
        mn, mx, std = float(non_null_num.min()), float(non_null_num.max()), float(non_null_num.std())

        # All values strictly between 0 and 1 → defect_rate
        if mn >= 0.0 and mx <= 1.0 and mx > 0.0:
            return "defect_rate", 0.80, "direct"

        # Values 0–100 that look like percentages → defect_rate (needs divide_by_100)
        if mn >= 0.0 and mx <= 100.0 and std < 20 and mx > 1.0:
            col_hint = _norm(col)
            if any(k in col_hint for k in ("defect", "reject", "fail", "quality", "error", "rate")):
                return "defect_rate", 0.75, "divide_by_100"

        # Large positive values with high variance → revenue or cost
        if mn >= 0 and mx > 10_000:
            col_hint = _norm(col)
            if any(k in col_hint for k in ("revenue", "sales", "income", "earning")):
                return "revenue", 0.70, "direct"
            if any(k in col_hint for k in ("transport", "shipping", "freight", "logistics")):
                return "transportation_cost", 0.70, "direct"
            if any(k in col_hint for k in ("manufactur", "production", "unit cost")):
                return "manufacturing_cost", 0.70, "direct"

        # Small non-negative integers → lead_time or delay days
        if mn >= 0 and mx <= 365 and std < 30:
            col_hint = _norm(col)
            if any(k in col_hint for k in ("lead", "lt")):
                return "lead_time_days", 0.70, "direct"
            if any(k in col_hint for k in ("delay", "late", "overdue")):
                return "delivery_delay_days", 0.70, "direct"

    # ── Datetime-like strings → timestamp ────────────────────────────────

    if series.dtype == object:
        parsed = pd.to_datetime(series.dropna().head(10), errors="coerce")
        if parsed.notna().mean() > 0.8:
            return "timestamp", 0.85, "date_parse"

    return None


# ── Main detect function ──────────────────────────────────────────────────────

def detect_mapping(csv_path: str) -> DetectionResult:
    """Detect column mapping using 3-layer rule-based approach (no LLM).

    For each source column:
      1. Try exact alias lookup (O(1))
      2. Try fuzzy match (rapidfuzz)
      3. Use dtype inference to confirm or break ties
    """
    df           = pd.read_csv(csv_path, nrows=200)   # read up to 200 rows for dtype inference
    source_cols  = list(df.columns)

    # canonical → best assignment so far: {source_col, confidence, transform, layer}
    assignments: Dict[str, Dict[str, Any]] = {}

    for col in source_cols:
        series = df[col]

        # ── Layer 1: exact ──────────────────────────────────────────────────
        l1 = _layer1(col)
        if l1:
            canonical, conf = l1
            _update_assignment(assignments, canonical, col, conf, "direct", "exact")
            continue

        # ── Layer 3: dtype (run before fuzzy to get a signal) ──────────────
        l3 = _layer3(col, series)

        # ── Layer 2: fuzzy ──────────────────────────────────────────────────
        l2 = _layer2(col)

        # Combine layers 2 and 3
        best = _combine(col, l2, l3)
        if best:
            canonical, conf, transform, layer = best
            _update_assignment(assignments, canonical, col, conf, transform, layer)

    # Build full canonical → FieldMapping dict
    mappings: Dict[str, FieldMapping] = {}
    for canonical in CANONICAL_FIELDS:
        asgn = assignments.get(canonical)
        if asgn:
            mappings[canonical] = FieldMapping(
                source_column=asgn["source_col"],
                transform=asgn["transform"],
                derive_formula=None,
                confidence=round(asgn["confidence"], 3),
                match_layer=asgn["layer"],
            )
        else:
            # Not found by any layer — mark as derived/default
            mappings[canonical] = FieldMapping(
                source_column=None,
                transform="derive",
                derive_formula="use_default",
                confidence=0.0,
                match_layer="none",
            )

    missing = [
        f for f, v in mappings.items()
        if v.source_column is None and CANONICAL_FIELDS[f]["required"]
    ]

    # Build summary note
    matched   = sum(1 for v in mappings.values() if v.source_column is not None)
    low_conf  = sum(1 for v in mappings.values() if 0 < v.confidence < _MEDIUM)
    notes = (
        f"Rule-based detection: {matched}/{len(CANONICAL_FIELDS)} fields mapped. "
        + (f"{low_conf} fields need user confirmation (confidence < {int(_MEDIUM*100)}%). " if low_conf else "")
        + (f"Missing required fields: {', '.join(missing)}." if missing else "All required fields found.")
    )

    logger.info("Detection complete — %s", notes)
    return DetectionResult(
        mappings=mappings,
        missing_fields=missing,
        notes=notes,
        source_columns=source_cols,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update_assignment(
    assignments: Dict[str, Dict[str, Any]],
    canonical: str,
    source_col: str,
    confidence: float,
    transform: str,
    layer: str,
) -> None:
    """Keep only the highest-confidence assignment per canonical field."""
    existing = assignments.get(canonical)
    if existing is None or confidence > existing["confidence"]:
        assignments[canonical] = {
            "source_col": source_col,
            "confidence": confidence,
            "transform":  transform,
            "layer":      layer,
        }


def _combine(
    col: str,
    l2: Optional[Tuple[str, float]],
    l3: Optional[Tuple[str, float, str]],
) -> Optional[Tuple[str, float, str, str]]:
    """Combine fuzzy (l2) and dtype (l3) results.

    Returns (canonical, confidence, transform, layer) or None.
    """
    if l3 and l2:
        canon_l3, conf_l3, tx_l3 = l3
        canon_l2, conf_l2        = l2

        if canon_l3 == canon_l2:
            # Both agree — boost confidence
            return canon_l3, min(max(conf_l3, conf_l2) + 0.05, 1.0), tx_l3, "fuzzy+dtype"

        # Disagree — prefer dtype if very confident, else prefer fuzzy
        if conf_l3 >= _HIGH:
            return canon_l3, conf_l3, tx_l3, "dtype"
        if conf_l2 >= _MEDIUM:
            return canon_l2, conf_l2, "direct", "fuzzy"
        return None

    if l3:
        canon_l3, conf_l3, tx_l3 = l3
        if conf_l3 >= _MEDIUM:
            return canon_l3, conf_l3, tx_l3, "dtype"

    if l2:
        canon_l2, conf_l2 = l2
        if conf_l2 >= _MEDIUM:
            return canon_l2, conf_l2, "direct", "fuzzy"

    return None
