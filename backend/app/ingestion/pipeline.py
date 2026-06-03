from __future__ import annotations

import asyncio
import logging
import pickle
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.config import get_settings
from app.database.connection import get_db_session, init_db
from app.database.models import (
    Incident,
    IncidentCategory,
    ResolutionStatus,
    RiskLevel,
    SeverityLevel,
    Supplier,
)
from app.ingestion.chunker import DocumentChunk, SupplyChainChunker, _calc_severity, _safe_float, _safe_str
from app.ingestion.embedder import OpenAIEmbedder
from app.retrieval.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)

# Path where BM25 artefacts are stored (relative to backend/)
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# ── BM25 index persistence ────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    import re
    return re.findall(r"[a-z0-9]+", text.lower())


def build_and_save_bm25(chunks: List[DocumentChunk]) -> None:
    from rank_bm25 import BM25Okapi

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    corpus_texts = [c.text for c in chunks]
    corpus_ids = [c.chunk_id for c in chunks]
    corpus_metadata = [c.metadata for c in chunks]

    tokenized = [_tokenize(t) for t in corpus_texts]
    bm25 = BM25Okapi(tokenized)

    with open(_DATA_DIR / "bm25_index.pkl", "wb") as f:
        pickle.dump(bm25, f)
    with open(_DATA_DIR / "bm25_corpus.pkl", "wb") as f:
        pickle.dump({"ids": corpus_ids, "texts": corpus_texts, "metadatas": corpus_metadata}, f)

    logger.info("BM25 index saved (%d documents).", len(corpus_texts))


# ── MySQL storage helpers ────────────────────────────────────────────────────

def _to_severity(val: str) -> SeverityLevel:
    mapping = {"critical": SeverityLevel.critical, "high": SeverityLevel.high,
               "medium": SeverityLevel.medium, "low": SeverityLevel.low}
    return mapping.get(val.lower(), SeverityLevel.medium)


def _to_incident_category(val: str) -> IncidentCategory:
    mapping = {"supplier": IncidentCategory.supplier, "shipment": IncidentCategory.shipment,
               "inventory": IncidentCategory.inventory, "demand": IncidentCategory.demand}
    return mapping.get(val.lower(), IncidentCategory.supplier)


def _to_resolution(val: str) -> ResolutionStatus:
    mapping = {"open": ResolutionStatus.open, "in_progress": ResolutionStatus.in_progress,
               "resolved": ResolutionStatus.resolved, "closed": ResolutionStatus.closed}
    return mapping.get(val.lower(), ResolutionStatus.open)


def _to_risk_level(severity: str) -> RiskLevel:
    mapping = {"critical": RiskLevel.critical, "high": RiskLevel.high,
               "medium": RiskLevel.medium, "low": RiskLevel.low}
    return mapping.get(severity.lower(), RiskLevel.low)


async def _upsert_suppliers(df: pd.DataFrame) -> Dict[str, str]:
    """Insert or update supplier records. Returns {supplier_id_str: db_pk_uuid}."""
    id_map: Dict[str, str] = {}

    async with get_db_session() as session:
        for supplier_id_raw, group in df.groupby("SupplierID", sort=False):
            supplier_id = str(supplier_id_raw)
            delays = [_safe_float(v) for v in group.get("DeliveryDelayDays", [])]
            reliabilities = [_safe_float(v) for v in group.get("ReliabilityScore", [])]
            avg_delay = sum(delays) / len(delays) if delays else 0.0
            avg_reliability = sum(reliabilities) / len(reliabilities) if reliabilities else 0.0

            inventories = [_safe_float(v, 100.0) for v in group.get("InventoryLevel", [])]
            demands = [_safe_float(v, 100.0) for v in group.get("DemandForecast", [])]
            severities = [_calc_severity(d, i, dm) for d, i, dm in zip(delays, inventories, demands)]
            critical = severities.count("critical")
            high = severities.count("high")
            overall = "critical" if critical >= 3 else "high" if high >= 3 or avg_delay > 10 else "medium" if avg_delay > 3 else "low"

            # Check if supplier already exists
            result = await session.execute(
                select(Supplier).where(Supplier.supplier_id == supplier_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.avg_delay_days = round(avg_delay, 2)
                existing.reliability_score = round(avg_reliability, 2)
                existing.risk_level = _to_risk_level(overall)
                existing.active_orders = int(len(group))
                db_pk = existing.id
            else:
                new_supplier = Supplier(
                    id=str(uuid.uuid4()),
                    supplier_id=supplier_id,
                    name=_safe_str(group["SupplierName"].iloc[0] if "SupplierName" in group.columns else None),
                    region=_safe_str(group["Region"].iloc[0] if "Region" in group.columns else None),
                    category=_safe_str(group["SupplierCategory"].iloc[0] if "SupplierCategory" in group.columns else None),
                    reliability_score=round(avg_reliability, 2),
                    avg_delay_days=round(avg_delay, 2),
                    active_orders=int(len(group)),
                    risk_level=_to_risk_level(overall),
                )
                session.add(new_supplier)
                db_pk = new_supplier.id

            id_map[supplier_id] = db_pk

    logger.info("Suppliers upserted: %d", len(id_map))
    return id_map


async def _insert_incidents(
    df: pd.DataFrame,
    supplier_pk_map: Dict[str, str],
    chunk_id_map: Dict[str, str],
) -> int:
    """Insert incident rows (skips rows whose incident_code already exists)."""
    inserted = 0

    async with get_db_session() as session:
        for idx, row in df.iterrows():
            incident_code = _safe_str(row.get("IncidentCode"), f"INC-{idx:05d}")

            # Skip duplicates
            result = await session.execute(
                select(Incident).where(Incident.incident_code == incident_code)
            )
            if result.scalar_one_or_none():
                continue

            supplier_id_str = _safe_str(row.get("SupplierID"))
            delay = _safe_float(row.get("DeliveryDelayDays"))
            inventory = _safe_float(row.get("InventoryLevel"), 100.0)
            demand = _safe_float(row.get("DemandForecast"), 100.0)
            severity_str = _calc_severity(delay, inventory, demand)

            occurred_at = None
            raw_date = row.get("OccurredAt")
            if raw_date is not None and pd.notna(raw_date):
                try:
                    occurred_at = pd.to_datetime(raw_date).to_pydatetime()
                except Exception:
                    pass

            incident = Incident(
                id=str(uuid.uuid4()),
                incident_code=incident_code,
                title=_safe_str(row.get("Title"), incident_code),
                description=_safe_str(row.get("Description")),
                severity=_to_severity(severity_str),
                category=_to_incident_category(_safe_str(row.get("IncidentCategory"), "supplier")),
                supplier_id=supplier_pk_map.get(supplier_id_str),
                supplier_ref=supplier_id_str,
                warehouse_location=_safe_str(row.get("WarehouseLocation")),
                shipment_status=_safe_str(row.get("ShipmentStatus")),
                delivery_delay_days=round(delay, 2),
                transportation_cost=round(_safe_float(row.get("TransportationCost")), 2),
                inventory_level=round(inventory, 2),
                demand_forecast=round(demand, 2),
                impact_score=round(_safe_float(row.get("ImpactScore"), severity_str == "critical" and 9.0 or 5.0), 2),
                resolution_status=_to_resolution(_safe_str(row.get("ResolutionStatus"), "open")),
                occurred_at=occurred_at,
                chroma_doc_id=chunk_id_map.get(incident_code),
            )
            session.add(incident)
            inserted += 1

            # Commit every 100 rows
            if inserted % 100 == 0:
                await session.flush()

    logger.info("Incidents inserted: %d", inserted)
    return inserted


# ── Main pipeline ────────────────────────────────────────────────────────────

class IngestionPipeline:
    def __init__(self) -> None:
        self.chunker = SupplyChainChunker()
        self.embedder = OpenAIEmbedder()
        self.vector_store = ChromaVectorStore()

    async def run(self, csv_path: str, reset_chroma: bool = False) -> Dict[str, Any]:
        t0 = time.perf_counter()
        settings = get_settings()

        # 0. Ensure DB tables exist
        await init_db()

        # 1. Load CSV
        logger.info("Loading CSV: %s", csv_path)
        df = pd.read_csv(csv_path)
        df = df.where(pd.notna(df), None)  # convert NaN → None
        logger.info("Loaded %d rows, %d columns.", len(df), len(df.columns))

        if reset_chroma:
            logger.warning("Resetting ChromaDB collection.")
            self.vector_store.delete_collection()
            self.vector_store = ChromaVectorStore()

        # 2. Chunk
        logger.info("Creating document chunks...")
        chunks = self.chunker.chunk_dataframe(df)
        logger.info("%d chunks created (%d record + %d supplier_summary).",
                    len(chunks),
                    sum(1 for c in chunks if c.chunk_type == "record"),
                    sum(1 for c in chunks if c.chunk_type == "supplier_summary"))

        # 3. Embed
        logger.info("Generating OpenAI embeddings...")
        texts = [c.text for c in chunks]
        embeddings = await self.embedder.embed_texts(texts)

        # 4. Store in ChromaDB
        logger.info("Storing in ChromaDB...")
        self.vector_store.add_documents(chunks, embeddings)
        logger.info("ChromaDB: %d total documents.", self.vector_store.count())

        # 5. Build BM25 index
        logger.info("Building BM25 index...")
        build_and_save_bm25(chunks)

        # chunk_id lookup by incident_code (for FK reference in incidents table)
        chunk_id_map = {
            c.metadata.get("incident_code", ""): c.chunk_id
            for c in chunks
            if c.chunk_type == "record"
        }

        # 6. MySQL — suppliers
        logger.info("Upserting suppliers into MySQL...")
        supplier_pk_map = await _upsert_suppliers(df)

        # 7. MySQL — incidents
        logger.info("Inserting incidents into MySQL...")
        n_inserted = await _insert_incidents(df, supplier_pk_map, chunk_id_map)

        elapsed = time.perf_counter() - t0
        summary = {
            "csv_rows": len(df),
            "chunks_created": len(chunks),
            "embeddings_generated": len(embeddings),
            "chroma_total": self.vector_store.count(),
            "suppliers_upserted": len(supplier_pk_map),
            "incidents_inserted": n_inserted,
            "elapsed_seconds": round(elapsed, 1),
        }
        logger.info("Ingestion complete in %.1fs: %s", elapsed, summary)
        return summary
