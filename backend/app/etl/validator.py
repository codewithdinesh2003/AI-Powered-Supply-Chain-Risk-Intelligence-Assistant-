"""Post-transform canonical DataFrame validation.

Fix 4: Hard failures vs soft warnings.
  HARD (skip row)  — both supplier identity fields null, completely empty row,
                     type is completely unparseable for a required numeric column.
  SOFT (keep, flag)— negative delays (early delivery), missing optional fields,
                     values outside typical ranges.
Target: 95%+ pass rate for clean datasets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

import pandas as pd

from app.etl.schemas import CANONICAL_FIELDS, REQUIRED_FIELDS

logger = logging.getLogger(__name__)

_VALID_SEVERITIES  = {"low", "medium", "high", "critical"}
_VALID_INSPECTIONS = {"Pass", "Fail", "Pending", "pass", "fail", "pending", "", "approved", "rejected"}


@dataclass
class ValidationResult:
    is_valid: bool
    valid_count: int        # rows that passed cleanly (no issues)
    warning_count: int      # rows kept but flagged with soft warnings
    failed_count: int       # rows skipped due to hard failures
    warnings: List[str] = field(default_factory=list)   # dataset-level warnings
    errors:   List[str] = field(default_factory=list)   # dataset-level errors
    row_warnings: List[Dict[str, Any]] = field(default_factory=list)  # soft per-row
    row_errors:   List[Dict[str, Any]] = field(default_factory=list)  # hard per-row

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid":       self.is_valid,
            "valid_count":    self.valid_count,
            "warning_count":  self.warning_count,
            "failed_count":   self.failed_count,
            "warnings":       self.warnings,
            "errors":         self.errors,
            "row_warnings":   self.row_warnings[:50],
            "row_errors":     self.row_errors[:50],
        }


class Validator:
    def validate(self, df: pd.DataFrame) -> ValidationResult:
        warnings: List[str] = []
        errors:   List[str] = []
        row_warnings: List[Dict[str, Any]] = []
        row_errors:   List[Dict[str, Any]] = []
        hard_failed:  Set[int] = set()
        soft_warned:  Set[int] = set()

        # ── Dataset-level required field checks ───────────────────────────
        for req in REQUIRED_FIELDS:
            if req not in df.columns:
                errors.append(f"Required field '{req}' missing after transformation.")

        # ── Optional field presence — dataset-level warnings only ─────────
        for opt in CANONICAL_FIELDS:
            if opt not in df.columns or df[opt].isna().all():
                if not CANONICAL_FIELDS[opt]["required"]:
                    warnings.append(f"Optional field '{opt}' absent — defaults applied.")

        # ── Per-row checks ────────────────────────────────────────────────
        for idx, row in df.iterrows():
            hard: List[str] = []
            soft: List[str] = []

            # ── HARD: identity missing ────────────────────────────────────
            has_id   = bool(row.get("supplier_id", ""))   and row.get("supplier_id")   != "nan"
            has_name = bool(row.get("supplier_name", "")) and row.get("supplier_name") != "nan"
            if not has_id and not has_name:
                hard.append("Both supplier_id and supplier_name are empty — cannot identify supplier.")

            # ── HARD: entirely null row ────────────────────────────────────
            key_cols = ["inventory_level", "demand_forecast", "warehouse_location",
                        "supplier_id", "supplier_name"]
            present  = [c for c in key_cols if c in df.columns and pd.notna(row.get(c)) and str(row.get(c, "")) not in ("", "nan", "0.0")]
            if len(present) == 0:
                hard.append("Row appears completely empty — no usable fields.")

            # ── SOFT: negative delay = early delivery ─────────────────────
            delay_val = row.get("delivery_delay_days")
            if delay_val is not None and pd.notna(delay_val):
                if float(delay_val) < 0:
                    soft.append(
                        f"delivery_delay_days={float(delay_val):.1f} (early delivery — kept as LOW risk)"
                    )

            # ── SOFT: defect_rate out of 0-1 (should have been normalised) ─
            defect_val = row.get("defect_rate")
            if defect_val is not None and pd.notna(defect_val):
                v = float(defect_val)
                if v < 0:
                    soft.append(f"defect_rate is negative ({v}) — clamped to 0.")
                    df.at[idx, "defect_rate"] = 0.0
                elif v > 1.0:
                    soft.append(f"defect_rate still > 1 ({v:.3f}) after normalisation — clamped to 1.")
                    df.at[idx, "defect_rate"] = 1.0

            # ── SOFT: severity enum check ─────────────────────────────────
            sev = str(row.get("severity", "")).lower()
            if sev and sev not in _VALID_SEVERITIES:
                soft.append(f"Unrecognised severity '{sev}' — defaulting to 'medium'.")
                df.at[idx, "severity"] = "medium"

            # ── SOFT: unusual inspection_status ───────────────────────────
            insp = str(row.get("inspection_status", ""))
            if insp and insp not in _VALID_INSPECTIONS:
                soft.append(f"Unusual inspection_status '{insp}'.")

            # Record results
            if hard:
                hard_failed.add(idx)
                row_errors.append({"row": idx, "errors": hard})
            elif soft:
                soft_warned.add(idx)
                row_warnings.append({"row": idx, "warnings": soft})

        total        = len(df)
        failed_count = len(hard_failed)
        warn_count   = len(soft_warned)
        valid_count  = total - failed_count - warn_count
        is_valid     = len(errors) == 0 and (valid_count + warn_count) > 0

        if failed_count:
            warnings.append(
                f"{failed_count} rows skipped (unrecoverable: missing identity)."
            )
        if warn_count:
            warnings.append(
                f"{warn_count} rows kept with soft warnings (e.g. early deliveries, clamped values)."
            )

        pass_rate = (valid_count + warn_count) / max(total, 1) * 100
        logger.info(
            "Validation: %d valid | %d warned | %d failed | pass-rate %.1f%%",
            valid_count, warn_count, failed_count, pass_rate,
        )

        return ValidationResult(
            is_valid=is_valid,
            valid_count=valid_count,
            warning_count=warn_count,
            failed_count=failed_count,
            warnings=warnings,
            errors=errors,
            row_warnings=row_warnings,
            row_errors=row_errors,
        )

    def filter_valid_rows(self, df: pd.DataFrame, result: ValidationResult) -> pd.DataFrame:
        """Drop ONLY hard-failed rows; rows with soft warnings are kept."""
        hard_indices = {r["row"] for r in result.row_errors}
        return df.drop(index=list(hard_indices)).reset_index(drop=True)
