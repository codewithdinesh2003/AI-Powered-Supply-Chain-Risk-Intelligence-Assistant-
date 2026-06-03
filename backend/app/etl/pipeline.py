"""ETL Pipeline orchestrator: Extract → Map → Transform → Derive → Validate → Load."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from app.etl.mapper import apply_mapping
from app.etl.schemas import CANONICAL_FIELDS
from app.etl.transformer import Transformer
from app.etl.validator import ValidationResult, Validator

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.anomaly_detector import AnomalyEvent

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[str, int], None]]  # (step_label, pct)


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class ETLResult:
    rows_processed: int
    rows_valid:     int    # clean rows, no issues
    rows_with_warnings: int = 0   # kept but flagged (e.g. early deliveries)
    rows_failed:    int = 0       # skipped — unrecoverable hard failures
    warnings: List[str] = field(default_factory=list)
    errors:   List[str] = field(default_factory=list)
    fields_derived: List[str] = field(default_factory=list)
    fields_missing: List[str] = field(default_factory=list)
    sample_output:  List[Dict[str, Any]] = field(default_factory=list)
    severity_distribution:         Dict[str, int] = field(default_factory=dict)
    shipment_status_distribution:  Dict[str, int] = field(default_factory=dict)
    job_id:             Optional[str] = None
    ingestion_summary:  Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rows_processed":               self.rows_processed,
            "rows_valid":                   self.rows_valid,
            "rows_with_warnings":           self.rows_with_warnings,
            "rows_failed":                  self.rows_failed,
            "warnings":                     self.warnings,
            "errors":                       self.errors,
            "fields_derived":               self.fields_derived,
            "fields_missing":               self.fields_missing,
            "sample_output":                self.sample_output,
            "severity_distribution":        self.severity_distribution,
            "shipment_status_distribution": self.shipment_status_distribution,
            "job_id":                       self.job_id,
            "ingestion_summary":            self.ingestion_summary,
        }


# ── In-memory ETL job store (shared with API route) ──────────────────────────

etl_jobs: Dict[str, Dict[str, Any]] = {}


async def _insert_anomaly_incidents(anomalies: List["AnomalyEvent"]) -> None:
    """Persist AnomalyEvent objects as open Incident rows so they appear in AlertFeed."""
    from app.database.connection import get_db_session
    from app.database.models import Incident, IncidentCategory, ResolutionStatus, SeverityLevel

    sev_map = {
        "critical": SeverityLevel.critical,
        "high":     SeverityLevel.high,
        "medium":   SeverityLevel.medium,
        "low":      SeverityLevel.low,
    }
    cat_map = {
        "defect_spike":        IncidentCategory.supplier,
        "stockout_risk":       IncidentCategory.inventory,
        "trend":               IncidentCategory.shipment,
        "statistical_outlier": IncidentCategory.supplier,
    }

    async with get_db_session() as db:
        for a in anomalies:
            incident = Incident(
                id=str(uuid.uuid4()),
                incident_code=f"ANO-{a.sku[:6].upper()}-{uuid.uuid4().hex[:4].upper()}",
                title=f"{a.sku}: {a.description[:80]}",
                description=a.description,
                severity=sev_map.get(a.severity, SeverityLevel.high),
                category=cat_map.get(a.anomaly_type, IncidentCategory.supplier),
                supplier_ref=a.supplier_name if a.supplier_name not in ("", "Multiple") else None,
                warehouse_location=a.location if a.location not in ("", "Multiple") else None,
                impact_score=90.0 if a.severity == "critical" else 70.0,
                resolution_status=ResolutionStatus.open,
                occurred_at=datetime.now(timezone.utc),
            )
            db.add(incident)
        await db.commit()
    logger.info("Inserted %d anomaly incidents into MySQL.", len(anomalies))


def _set_job(job_id: str, **kwargs) -> None:
    if job_id in etl_jobs:
        etl_jobs[job_id].update(kwargs)


# ── ETL Pipeline ─────────────────────────────────────────────────────────────

class ETLPipeline:
    def __init__(self) -> None:
        self._transformer = Transformer()
        self._validator   = Validator()

    # ── Full pipeline ─────────────────────────────────────────────────────

    async def run(
        self,
        csv_path: str,
        mapping: Dict[str, Any],
        company_id: str = "default",
        job_id: Optional[str] = None,
    ) -> ETLResult:
        def _progress(step: str, pct: int) -> None:
            if job_id:
                _set_job(job_id, step=step, progress=pct, status="processing")

        try:
            # ── 1. Extract ─────────────────────────────────────────────────
            _progress("Extracting CSV data...", 5)
            raw_df = pd.read_csv(csv_path)
            raw_df = raw_df.where(pd.notna(raw_df), None)
            rows_total = len(raw_df)
            _progress(f"Loaded {rows_total:,} rows.", 10)

            await asyncio.sleep(0)  # yield

            # ── 2. Map columns ─────────────────────────────────────────────
            _progress("Applying column mapping...", 15)
            mapped_df = apply_mapping(raw_df, mapping)

            # ── 3. Cast types ──────────────────────────────────────────────
            _progress("Normalising data types...", 25)
            typed_df = self._transformer.cast_types(mapped_df)

            # ── 4. Derive fields ───────────────────────────────────────────
            _progress("Deriving computed fields...", 35)
            enriched_df, derived_fields = self._transformer.derive_fields(typed_df)

            # Missing fields = canonical fields absent AFTER all derivations
            # (check here, not before, so derived fields like supplier_id are not false-flagged)
            missing_fields = [
                f for f in CANONICAL_FIELDS
                if f not in enriched_df.columns or enriched_df[f].isna().all()
                   or (enriched_df[f].dtype == object and enriched_df[f].eq("").all())
            ]

            # ── 4b. Anomaly detection (runs on enriched data, non-blocking) ─
            _progress("Running anomaly detection...", 48)
            try:
                from app.agents.anomaly_detector import AnomalyDetector
                anomalies = AnomalyDetector().detect(enriched_df)
                _progress(f"Detected {len(anomalies)} anomalies.", 50)
                if anomalies:
                    n_crit = sum(1 for a in anomalies if a.severity == "critical")
                    logger.info("Anomaly detection: %d events — %d critical", len(anomalies), n_crit)
                    await _insert_anomaly_incidents(anomalies)
            except Exception as _anom_exc:
                logger.warning("Anomaly detection failed (non-fatal): %s", _anom_exc)

            # ── 5. Validate ────────────────────────────────────────────────
            _progress("Validating rows...", 52)
            val_result: ValidationResult = self._validator.validate(enriched_df)
            valid_df = self._validator.filter_valid_rows(enriched_df, val_result)

            # ── 6. Convert to pipeline format ──────────────────────────────
            _progress("Preparing for ingestion...", 60)
            pipeline_df = self._transformer.to_pipeline_format(valid_df)

            # ── 7. Compute distributions (severity + shipment_status) ───────
            distributions = Transformer.compute_distributions(enriched_df)

            # ── 8. Load via ingestion pipeline ─────────────────────────────
            _progress("Generating embeddings...", 65)
            ingestion_summary = await self._load(pipeline_df, company_id, _progress)

            rows_ingested = val_result.valid_count + val_result.warning_count
            _progress("Complete!", 100)
            if job_id:
                _set_job(
                    job_id,
                    status="completed",
                    records_processed=rows_ingested,
                    suppliers_detected=ingestion_summary.get("suppliers_upserted", 0),
                )

            return ETLResult(
                rows_processed=rows_total,
                rows_valid=val_result.valid_count,
                rows_with_warnings=val_result.warning_count,
                rows_failed=val_result.failed_count,
                warnings=val_result.warnings,
                errors=val_result.errors,
                fields_derived=list(set(derived_fields)),
                fields_missing=missing_fields,
                sample_output=valid_df.head(3).fillna("").to_dict("records"),
                severity_distribution=distributions.get("severity", {}),
                shipment_status_distribution=distributions.get("shipment_status", {}),
                job_id=job_id,
                ingestion_summary=ingestion_summary,
            )

        except Exception as exc:
            logger.error("ETL pipeline error: %s", exc, exc_info=True)
            if job_id:
                _set_job(job_id, status="failed", step=f"Error: {exc}", errors=[str(exc)])
            return ETLResult(
                rows_processed=0, rows_valid=0, rows_with_warnings=0, rows_failed=0,
                errors=[str(exc)], job_id=job_id,
            )

    async def _load(self, pipeline_df: pd.DataFrame, company_id: str, progress_fn: Callable) -> Dict[str, Any]:
        from app.ingestion.chunker import SupplyChainChunker
        from app.ingestion.embedder import OpenAIEmbedder
        from app.ingestion.pipeline import (
            _insert_incidents,
            _upsert_suppliers,
            build_and_save_bm25,
        )
        from app.retrieval.vector_store import ChromaVectorStore

        chunker      = SupplyChainChunker()
        embedder     = OpenAIEmbedder()
        vector_store = ChromaVectorStore()

        progress_fn("Chunking documents...", 65)
        chunks = chunker.chunk_dataframe(pipeline_df)

        progress_fn("Generating embeddings...", 68)
        texts      = [c.text for c in chunks]
        embeddings = await embedder.embed_texts(texts)

        progress_fn("Indexing in ChromaDB...", 82)
        vector_store.add_documents(chunks, embeddings)

        progress_fn("Building BM25 index...", 88)
        build_and_save_bm25(chunks)

        progress_fn("Storing in MySQL...", 90)
        chunk_id_map = {c.metadata.get("incident_code", ""): c.chunk_id
                        for c in chunks if c.chunk_type == "record"}
        supplier_pk_map = await _upsert_suppliers(pipeline_df)
        n_inserted      = await _insert_incidents(pipeline_df, supplier_pk_map, chunk_id_map)

        return {
            "chunks_created":    len(chunks),
            "suppliers_upserted": len(supplier_pk_map),
            "incidents_inserted": n_inserted,
            "chroma_total":      vector_store.count(),
        }

    # ── Preview (no DB write) ─────────────────────────────────────────────

    async def preview(self, csv_path: str, mapping: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Transform up to 10 rows and return them — does NOT write to DB."""
        raw_df    = pd.read_csv(csv_path, nrows=10)
        raw_df    = raw_df.where(pd.notna(raw_df), None)
        mapped    = apply_mapping(raw_df, mapping)
        typed     = self._transformer.cast_types(mapped)
        enriched, _ = self._transformer.derive_fields(typed)
        return enriched.fillna("").head(10).to_dict("records")
