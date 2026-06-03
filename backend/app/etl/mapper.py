"""Apply a confirmed column mapping to a raw DataFrame → canonical DataFrame."""
from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

from app.etl.schemas import CANONICAL_FIELDS, TRANSFORM_DERIVE, TRANSFORM_DIRECT

logger = logging.getLogger(__name__)


def apply_mapping(raw_df: pd.DataFrame, mapping: Dict[str, Any]) -> pd.DataFrame:
    """Rename / derive columns according to a confirmed mapping config.

    ``mapping`` is the ``mappings`` sub-dict from :class:`DetectionResult`:
    ``{canonical_field: {source_column, transform, derive_formula, confidence}}``
    """
    canonical_df = pd.DataFrame()

    for canonical_field, spec in mapping.items():
        if canonical_field not in CANONICAL_FIELDS:
            continue

        source_col = spec.get("source_column")
        transform  = spec.get("transform", TRANSFORM_DIRECT)
        formula    = spec.get("derive_formula")

        if source_col and source_col in raw_df.columns:
            series = raw_df[source_col].copy()

            if transform == "divide_by_100":
                series = pd.to_numeric(series, errors="coerce") / 100.0
            elif transform == "negate":
                series = -pd.to_numeric(series, errors="coerce")
            elif transform == "date_parse":
                series = pd.to_datetime(series, errors="coerce").astype(str)
            elif transform == "slugify":
                series = (
                    series.astype(str)
                    .str.lower()
                    .str.replace(r"[^a-z0-9]+", "-", regex=True)
                    .str.strip("-")
                )

            canonical_df[canonical_field] = series

        elif transform == TRANSFORM_DERIVE:
            # Handled in transformer.py — leave as NaN placeholder for now
            canonical_df[canonical_field] = pd.NA

        else:
            canonical_df[canonical_field] = pd.NA

    # Carry through any extra columns from the raw DF that may be useful
    for col in raw_df.columns:
        if col not in canonical_df.columns:
            canonical_df[f"_raw_{col}"] = raw_df[col]

    canonical_df.reset_index(drop=True, inplace=True)
    return canonical_df
