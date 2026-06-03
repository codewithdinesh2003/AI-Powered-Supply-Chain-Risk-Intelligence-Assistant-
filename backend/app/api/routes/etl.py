"""ETL API routes — detect mapping, preview, run full ETL, manage saved mappings."""
from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.middleware import get_current_user, ok
from app.database.models import User
from app.etl.detector import detect_mapping
from app.etl.mapping_store import MappingStore
from app.etl.pipeline import ETLPipeline, etl_jobs

logger = logging.getLogger(__name__)
router = APIRouter()

_UPLOAD_DIR = Path(tempfile.gettempdir()) / "scm_etl"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# temp_files store: {temp_id: csv_path}
_temp_files: Dict[str, str] = {}

_store = MappingStore()


# ── Schemas ────────────────────────────────────────────────────────────────────

class FieldMappingSpec(BaseModel):
    source_column:  Optional[str]
    transform:      str = "direct"
    derive_formula: Optional[str] = None
    confidence:     float = 1.0


class PreviewRequest(BaseModel):
    temp_file_id: str
    mapping:      Dict[str, FieldMappingSpec]


class ETLRunRequest(BaseModel):
    temp_file_id:  str
    mapping:       Dict[str, FieldMappingSpec]
    company_id:    str = "default"
    company_name:  str = "Default Company"
    save_mapping:  bool = False


class SaveMappingRequest(BaseModel):
    company_id:       str
    company_name:     str
    mapping_config:   Dict[str, Any]
    source_columns:   List[str] = []
    confidence_score: float = 0.8


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mapping_to_dict(mapping: Dict[str, FieldMappingSpec]) -> Dict[str, Any]:
    return {k: v.model_dump() for k, v in mapping.items()}


def _save_upload(contents: bytes, filename: str) -> tuple[str, str]:
    temp_id  = str(uuid.uuid4())
    csv_path = str(_UPLOAD_DIR / f"{temp_id}_{filename}")
    Path(csv_path).write_bytes(contents)
    _temp_files[temp_id] = csv_path
    return temp_id, csv_path


def _get_temp_path(temp_file_id: str) -> str:
    path = _temp_files.get(temp_file_id)
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Temp file not found — re-upload the CSV.")
    return path


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/detect")
async def detect(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    """Upload CSV, run LLM auto-detection of column mapping. Returns temp_file_id + detected mapping."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    temp_id, csv_path = _save_upload(contents, file.filename)

    try:
        # Rule-based detection — synchronous, no LLM
        detection = detect_mapping(csv_path)
    except Exception as exc:
        logger.error("Column detection failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}")

    # Check if a saved mapping exists for detection context
    existing = None
    try:
        # Attempt to match by source column similarity (simple heuristic)
        all_mappings = await _store.list_all()
        for saved in all_mappings:
            saved_cols = set(saved.get("source_columns") or [])
            detected_cols = set(detection.source_columns)
            overlap = len(saved_cols & detected_cols) / max(len(saved_cols | detected_cols), 1)
            if overlap > 0.7:
                existing = saved
                break
    except Exception:
        pass

    return ok(
        {
            "temp_file_id":    temp_id,
            "detected_mapping": detection.to_dict(),
            "saved_mapping":   existing,
            "filename":        file.filename,
            "row_count":       len(pd.read_csv(csv_path, nrows=1000)),
        }
    )


@router.post("/preview")
async def preview(
    req: PreviewRequest,
    _: User = Depends(get_current_user),
):
    """Apply the given mapping to the temp CSV and return 10 transformed rows."""
    csv_path = _get_temp_path(req.temp_file_id)
    mapping_dict = _mapping_to_dict(req.mapping)

    pipeline = ETLPipeline()
    try:
        rows = await pipeline.preview(csv_path, mapping_dict)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Preview failed: {exc}")

    return ok({"rows": rows, "count": len(rows)})


@router.post("/run")
async def run_etl(
    req: ETLRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Confirm mapping and start full ETL + ingestion as a background job."""
    csv_path    = _get_temp_path(req.temp_file_id)
    mapping_dict = _mapping_to_dict(req.mapping)
    job_id      = str(uuid.uuid4())

    # Extract original filename from temp path (format: {uuid}_{original_name})
    _temp_basename = Path(csv_path).name
    _original_filename = _temp_basename[37:] if len(_temp_basename) > 37 else _temp_basename

    # Register job (include filename so upload history can display it)
    from datetime import datetime, timezone as _tz
    etl_jobs[job_id] = {
        "job_id":             job_id,
        "filename":           _original_filename,   # shown in upload history
        "company_name":       req.company_name,
        "status":             "pending",
        "step":               "Queued",
        "progress":           0,
        "total_records":      0,
        "records_processed":  0,
        "suppliers_detected": 0,
        "errors":             [],
        "result":             None,
        "created_at":         datetime.now(_tz.utc).isoformat(),
        "completed_at":       None,
        "source":             "etl",
    }

    # Save mapping if requested
    if req.save_mapping:
        try:
            await _store.save(
                company_id=req.company_id,
                company_name=req.company_name,
                mapping_config=mapping_dict,
                source_columns=list(pd.read_csv(csv_path, nrows=0).columns),
                confidence_score=0.95,
                user_id=str(current_user.id),
            )
        except Exception as exc:
            logger.warning("Mapping save failed (non-fatal): %s", exc)

    async def _bg_run():
        pipeline = ETLPipeline()
        result   = await pipeline.run(
            csv_path=csv_path,
            mapping=mapping_dict,
            company_id=req.company_id,
            job_id=job_id,
        )
        etl_jobs[job_id]["result"] = result.to_dict()
        try:
            Path(csv_path).unlink(missing_ok=True)
            _temp_files.pop(req.temp_file_id, None)
        except Exception:
            pass

    background_tasks.add_task(_bg_run)

    return ok(
        {"job_id": job_id, "status": "processing", "message": "ETL pipeline started."},
        meta={"company_id": req.company_id},
    )


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    _: User = Depends(get_current_user),
):
    job = etl_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="ETL job not found.")
    return ok(job)


# ── Mapping CRUD ───────────────────────────────────────────────────────────────

@router.get("/mappings")
async def list_mappings(_: User = Depends(get_current_user)):
    mappings = await _store.list_all()
    return ok(mappings, meta={"count": len(mappings)})


@router.post("/mappings", status_code=201)
async def save_mapping(
    req: SaveMappingRequest,
    current_user: User = Depends(get_current_user),
):
    saved_id = await _store.save(
        company_id=req.company_id,
        company_name=req.company_name,
        mapping_config=req.mapping_config,
        source_columns=req.source_columns,
        confidence_score=req.confidence_score,
        user_id=str(current_user.id),
    )
    return ok({"id": saved_id, "company_id": req.company_id})


@router.put("/mappings/{mapping_id}")
async def update_mapping(
    mapping_id: str,
    req: SaveMappingRequest,
    current_user: User = Depends(get_current_user),
):
    existing = await _store.get_by_id(mapping_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Mapping not found.")
    saved_id = await _store.save(
        company_id=req.company_id,
        company_name=req.company_name,
        mapping_config=req.mapping_config,
        source_columns=req.source_columns,
        confidence_score=req.confidence_score,
        user_id=str(current_user.id),
    )
    return ok({"id": saved_id})


@router.delete("/mappings/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: str,
    _: User = Depends(get_current_user),
):
    deleted = await _store.delete(mapping_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found.")
