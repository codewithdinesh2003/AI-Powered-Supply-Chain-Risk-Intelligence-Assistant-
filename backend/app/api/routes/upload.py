"""CSV upload + background ingestion endpoint.

Flow:
  POST /upload/csv         → validate, save to /tmp, start background job, return job_id
  GET  /upload/status/{id} → poll in-memory job store for progress
  GET  /upload/history     → list all jobs (in-memory, resets on restart)
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.api.middleware import get_current_user, ok
from app.database.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Upload directory ──────────────────────────────────────────────────────────

_UPLOAD_DIR = Path(tempfile.gettempdir()) / "scm_uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# ── In-memory job store ───────────────────────────────────────────────────────

@dataclass
class JobState:
    job_id: str
    original_filename: str
    csv_path: str
    status: str = "pending"       # pending / processing / completed / failed
    step: str = "Queued"
    progress: int = 0             # 0–100
    total_records: int = 0
    records_processed: int = 0
    suppliers_detected: int = 0
    errors: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.original_filename,
            "status": self.status,
            "step": self.step,
            "progress": self.progress,
            "total_records": self.total_records,
            "records_processed": self.records_processed,
            "suppliers_detected": self.suppliers_detected,
            "errors": self.errors,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


_jobs: Dict[str, JobState] = {}


def _set(job_id: str, **kwargs) -> None:
    """Helper to patch fields on a job atomically."""
    job = _jobs.get(job_id)
    if job is None:
        return
    for k, v in kwargs.items():
        setattr(job, k, v)


# ── Column normalizer ─────────────────────────────────────────────────────────

# Maps lowercase/underscore variants → pipeline PascalCase column names
_COL_MAP: Dict[str, str] = {
    "supplier_id": "SupplierID", "supplierid": "SupplierID",
    "supplier_name": "SupplierName", "suppliername": "SupplierName",
    "region": "Region",
    "supplier_category": "SupplierCategory", "suppliercategory": "SupplierCategory", "category": "SupplierCategory",
    "reliability_score": "ReliabilityScore", "reliabilityscore": "ReliabilityScore",
    "inventory_level": "InventoryLevel", "inventorylevel": "InventoryLevel",
    "shipment_status": "ShipmentStatus", "shipmentstatus": "ShipmentStatus",
    "warehouse_location": "WarehouseLocation", "warehouselocation": "WarehouseLocation",
    "delivery_delay": "DeliveryDelayDays", "deliverydelay": "DeliveryDelayDays",
    "delivery_delay_days": "DeliveryDelayDays", "deliverydelaydays": "DeliveryDelayDays",
    "transportation_cost": "TransportationCost", "transportationcost": "TransportationCost",
    "order_quantity": "DemandForecast", "orderquantity": "DemandForecast",
    "demand_forecast": "DemandForecast", "demandforecast": "DemandForecast",
    "timestamp": "OccurredAt", "occurred_at": "OccurredAt", "occurredat": "OccurredAt",
    "date": "OccurredAt",
    "title": "Title", "description": "Description",
    "incident_code": "IncidentCode", "incidentcode": "IncidentCode",
    "incident_category": "IncidentCategory", "incidentcategory": "IncidentCategory",
    "resolution_status": "ResolutionStatus", "resolutionstatus": "ResolutionStatus",
    "impact_score": "ImpactScore", "impactscore": "ImpactScore",
}

# At least one alias from each group must appear in the CSV
_REQUIRED_GROUPS = [
    ["supplier_id", "supplierid"],
    ["inventory_level", "inventorylevel"],
    ["shipment_status", "shipmentstatus"],
    ["warehouse_location", "warehouselocation"],
    ["delivery_delay", "delivery_delay_days", "deliverydelay", "deliverydelaydays"],
    ["transportation_cost", "transportationcost"],
    ["demand_forecast", "demandforecast", "order_quantity", "orderquantity"],
    ["timestamp", "occurred_at", "date", "occurredat"],
]


def _normalize_and_validate(df: pd.DataFrame) -> tuple[pd.DataFrame, List[str]]:
    """Rename columns to PascalCase pipeline format. Return (renamed_df, missing_groups)."""
    lower_cols = {c.lower().replace(" ", "_"): c for c in df.columns}

    rename_map = {}
    for lower_key, original in lower_cols.items():
        stripped = lower_key.replace("_", "")
        if lower_key in _COL_MAP:
            rename_map[original] = _COL_MAP[lower_key]
        elif stripped in _COL_MAP:
            rename_map[original] = _COL_MAP[stripped]

    df = df.rename(columns=rename_map)

    # Check required groups
    present_lower = {c.lower().replace("_", "") for c in df.columns}
    missing = []
    for group in _REQUIRED_GROUPS:
        group_stripped = [g.replace("_", "") for g in group]
        if not any(g in present_lower for g in group_stripped):
            missing.append(group[0])   # report canonical name

    return df, missing


# ── Background ingestion task ─────────────────────────────────────────────────

async def _run_ingestion(job_id: str, csv_path: str) -> None:
    from app.ingestion.chunker import SupplyChainChunker
    from app.ingestion.embedder import OpenAIEmbedder
    from app.ingestion.pipeline import (
        _insert_incidents,
        _upsert_suppliers,
        build_and_save_bm25,
    )
    from app.retrieval.vector_store import ChromaVectorStore

    job = _jobs[job_id]

    try:
        # ── Step 1: Parse CSV ──────────────────────────────────────────────
        _set(job_id, status="processing", step="Parsing CSV...", progress=5)
        df = pd.read_csv(csv_path)
        df = df.where(pd.notna(df), None)
        df, missing = _normalize_and_validate(df)

        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        total = len(df)
        _set(job_id, total_records=total, progress=12,
             step=f"CSV parsed — {total:,} rows found")

        await asyncio.sleep(0.1)  # yield to event loop

        # ── Step 2: Chunk ───────────────────────────────────────────────────
        _set(job_id, step="Analyzing supply chain events...", progress=14)
        chunker = SupplyChainChunker()
        chunks = chunker.chunk_dataframe(df)
        _set(job_id, progress=16)

        # ── Step 3: Embed ───────────────────────────────────────────────────
        _set(job_id, step="Generating embeddings...", progress=16)
        embedder = OpenAIEmbedder()
        texts = [c.text for c in chunks]
        embeddings = await embedder.embed_texts(texts)
        _set(job_id, progress=55)

        # ── Step 4: ChromaDB ────────────────────────────────────────────────
        _set(job_id, step="Indexing in ChromaDB...", progress=55)
        vector_store = ChromaVectorStore()
        vector_store.add_documents(chunks, embeddings)
        _set(job_id, progress=68)

        # ── Step 5: BM25 ────────────────────────────────────────────────────
        _set(job_id, step="Building BM25 index...", progress=68)
        build_and_save_bm25(chunks)
        _set(job_id, progress=75)

        # ── Step 6: MySQL ────────────────────────────────────────────────────
        _set(job_id, step="Storing in MySQL...", progress=75)
        chunk_id_map = {
            c.metadata.get("incident_code", ""): c.chunk_id
            for c in chunks if c.chunk_type == "record"
        }
        supplier_pk_map = await _upsert_suppliers(df)
        n_inserted = await _insert_incidents(df, supplier_pk_map, chunk_id_map)
        _set(job_id, progress=95, records_processed=n_inserted,
             suppliers_detected=len(supplier_pk_map))

        # ── Done ─────────────────────────────────────────────────────────────
        _set(
            job_id,
            status="completed",
            step="Complete!",
            progress=100,
            completed_at=datetime.now(timezone.utc),
        )
        logger.info("Ingestion job %s completed: %d records, %d suppliers.", job_id, n_inserted, len(supplier_pk_map))

    except Exception as exc:
        logger.error("Ingestion job %s failed: %s", job_id, exc, exc_info=True)
        _set(job_id, status="failed", step=f"Failed: {exc}", errors=[str(exc)])

    finally:
        # Clean up temp file
        try:
            Path(csv_path).unlink(missing_ok=True)
        except Exception:
            pass


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/csv")
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    # ── Validate file type ────────────────────────────────────────────────
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    # ── Read and validate size ────────────────────────────────────────────
    contents = await file.read()
    if len(contents) > _MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 50 MB limit.")
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ── Quick column check before saving ─────────────────────────────────
    import io
    try:
        preview_df = pd.read_csv(io.BytesIO(contents), nrows=5)
        _, missing = _normalize_and_validate(preview_df.copy())
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"CSV is missing required columns: {', '.join(missing)}. "
                       f"Found columns: {list(preview_df.columns)}",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")

    # ── Save to temp directory ────────────────────────────────────────────
    job_id = str(uuid.uuid4())
    safe_name = f"{job_id}_{file.filename.replace(' ', '_')}"
    csv_path = str(_UPLOAD_DIR / safe_name)
    Path(csv_path).write_bytes(contents)

    # ── Register job ──────────────────────────────────────────────────────
    _jobs[job_id] = JobState(
        job_id=job_id,
        original_filename=file.filename,
        csv_path=csv_path,
    )

    # ── Kick off background ingestion ─────────────────────────────────────
    background_tasks.add_task(_run_ingestion, job_id, csv_path)

    return ok(
        {"job_id": job_id, "status": "processing", "message": "Ingestion started."},
        meta={"filename": file.filename, "size_bytes": len(contents)},
    )


@router.get("/status/{job_id}")
async def get_status(
    job_id: str,
    _: User = Depends(get_current_user),
):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return ok(job.to_dict())


@router.get("/history")
async def get_history(
    _: User = Depends(get_current_user),
):
    # Combine simple-upload jobs and ETL pipeline jobs
    from app.etl.pipeline import etl_jobs

    simple = [j.to_dict() for j in _jobs.values()]

    etl = [
        {
            "job_id":             j.get("job_id", ""),
            "filename":           j.get("filename", "etl-upload.csv"),
            "status":             j.get("status", "pending"),
            "step":               j.get("step", ""),
            "progress":           j.get("progress", 0),
            "total_records":      j.get("total_records", 0),
            "records_processed":  j.get("records_processed", 0),
            "suppliers_detected": j.get("suppliers_detected", 0),
            "errors":             j.get("errors", []),
            "created_at":         j.get("created_at", ""),
            "completed_at":       j.get("completed_at"),
            "source":             "etl",
        }
        for j in etl_jobs.values()
    ]

    history = sorted(
        simple + etl,
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )
    return ok(history, meta={"count": len(history)})


@router.get("/preview")
async def preview_csv(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    """Return first 10 rows of a CSV for preview before committing to upload."""
    contents = await file.read(1024 * 512)  # read max 512 KB for preview
    import io
    try:
        df = pd.read_csv(io.BytesIO(contents), nrows=10)
        return ok({
            "columns": list(df.columns),
            "rows": df.fillna("").to_dict(orient="records"),
            "total_preview_rows": len(df),
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")
