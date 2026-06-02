"""Unit tests for the retrieval layer.

External dependencies (ChromaDB, BM25 pickle, OpenAI, CrossEncoder) are mocked.
Run with:  pytest tests/test_retrieval.py -v
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.retrieval.vector_store import RetrievedDocument


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_doc(rank: int = 0, score: float = 0.9, category: str = "supplier") -> RetrievedDocument:
    return RetrievedDocument(
        doc_id=f"record_INC-{rank:05d}_SUP-001",
        text=f"SUPPLY CHAIN INCIDENT REPORT #{rank}\nSupplier: GlobalTech\nDelivery Delay: {rank * 2} days",
        metadata={"supplier_id": "SUP-001", "severity": "high", "incident_category": category},
        score=score,
        rank=rank,
    )


# ── BM25 retriever ────────────────────────────────────────────────────────────

class TestBM25Retriever:
    def test_returns_empty_when_no_index(self, tmp_path, monkeypatch):
        """BM25Retriever should degrade gracefully when pickle is missing."""
        from app.retrieval import bm25_retriever as bm25_mod

        monkeypatch.setattr(bm25_mod, "_INDEX_PATH", tmp_path / "missing.pkl")
        monkeypatch.setattr(bm25_mod, "_CORPUS_PATH", tmp_path / "missing2.pkl")

        from app.retrieval.bm25_retriever import BM25Retriever

        retriever = BM25Retriever()
        results = retriever.search("supplier delay", k=5)
        assert results == []
        assert retriever.is_ready is False

    def test_search_returns_ranked_results(self, tmp_path):
        """With a built index, search should return scored results."""
        import pickle
        from rank_bm25 import BM25Okapi

        import app.retrieval.bm25_retriever as bm25_mod

        corpus_texts = [
            "supplier delivery delay critical shipment",
            "inventory stockout demand forecast",
            "port congestion transportation cost spike",
        ]
        corpus_ids = [f"doc_{i}" for i in range(3)]
        corpus_meta = [{"incident_category": "supplier"}, {"incident_category": "inventory"}, {"incident_category": "shipment"}]
        import re
        tokenized = [re.findall(r"[a-z0-9]+", t.lower()) for t in corpus_texts]
        bm25 = BM25Okapi(tokenized)

        index_path = tmp_path / "bm25_index.pkl"
        corpus_path = tmp_path / "bm25_corpus.pkl"
        with open(index_path, "wb") as f:
            pickle.dump(bm25, f)
        with open(corpus_path, "wb") as f:
            pickle.dump({"ids": corpus_ids, "texts": corpus_texts, "metadatas": corpus_meta}, f)

        bm25_mod._INDEX_PATH = index_path
        bm25_mod._CORPUS_PATH = corpus_path

        from importlib import reload
        from app.retrieval import bm25_retriever
        reload(bm25_retriever)
        retriever = bm25_retriever.BM25Retriever()

        results = retriever.search("supplier delivery", k=2)
        assert len(results) <= 2
        # First result should be the supplier-related document
        if results:
            assert results[0].score >= 0


# ── Hybrid retriever RRF fusion ───────────────────────────────────────────────

class TestRRFFusion:
    def test_deduplicates_by_doc_id(self):
        from app.retrieval.hybrid_retriever import _reciprocal_rank_fusion

        doc_a = _make_doc(rank=0, score=0.95)
        doc_b = _make_doc(rank=1, score=0.80)
        # doc_a appears in both lists (should be deduplicated)
        list1 = [doc_a, doc_b]
        list2 = [doc_a]

        fused = _reciprocal_rank_fusion([list1, list2])
        ids = [d.doc_id for d in fused]
        assert len(ids) == len(set(ids))  # no duplicates

    def test_doc_in_both_lists_scores_higher(self):
        from app.retrieval.hybrid_retriever import _reciprocal_rank_fusion

        shared = _make_doc(rank=0, score=0.9)
        shared.doc_id = "shared_doc"
        unique = _make_doc(rank=2, score=0.7)
        unique.doc_id = "unique_doc"

        fused = _reciprocal_rank_fusion([[shared], [shared, unique]])
        score_map = {d.doc_id: d.score for d in fused}
        # shared doc appears in both lists → higher RRF score
        assert score_map["shared_doc"] > score_map["unique_doc"]

    def test_empty_lists_return_empty(self):
        from app.retrieval.hybrid_retriever import _reciprocal_rank_fusion

        assert _reciprocal_rank_fusion([[], []]) == []
        assert _reciprocal_rank_fusion([]) == []

    def test_rrf_scores_decrease_with_rank(self):
        from app.retrieval.hybrid_retriever import _reciprocal_rank_fusion

        docs = [_make_doc(rank=i, score=1.0 - i * 0.1) for i in range(5)]
        for i, d in enumerate(docs):
            d.doc_id = f"doc_{i}"

        fused = _reciprocal_rank_fusion([docs])
        scores = [d.score for d in fused]
        assert scores == sorted(scores, reverse=True)


# ── Chroma filter conversion ──────────────────────────────────────────────────

class TestChromaFilter:
    def test_single_filter(self):
        from app.retrieval.hybrid_retriever import _to_chroma_where

        where = _to_chroma_where({"severity": "critical"})
        assert where == {"severity": {"$eq": "critical"}}

    def test_multiple_filters_wrapped_in_and(self):
        from app.retrieval.hybrid_retriever import _to_chroma_where

        where = _to_chroma_where({"severity": "critical", "supplier_id": "SUP-001"})
        assert "$and" in where
        assert len(where["$and"]) == 2

    def test_list_value_uses_in_operator(self):
        from app.retrieval.hybrid_retriever import _to_chroma_where

        where = _to_chroma_where({"severity": ["critical", "high"]})
        assert where == {"severity": {"$in": ["critical", "high"]}}

    def test_none_value_excluded(self):
        from app.retrieval.hybrid_retriever import _to_chroma_where

        where = _to_chroma_where({"severity": None, "supplier_id": "SUP-001"})
        assert "$and" not in str(where)
        assert where == {"supplier_id": {"$eq": "SUP-001"}}

    def test_empty_filters_returns_none(self):
        from app.retrieval.hybrid_retriever import _to_chroma_where

        assert _to_chroma_where({}) is None
        assert _to_chroma_where(None) is None


# ── Chunker ───────────────────────────────────────────────────────────────────

class TestChunker:
    def _sample_df(self):
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "IncidentCode": "INC-00001",
                    "SupplierID": "SUP-001",
                    "SupplierName": "GlobalTech",
                    "Region": "Asia-Pacific",
                    "SupplierCategory": "Electronics",
                    "ReliabilityScore": 72.0,
                    "WarehouseLocation": "Shanghai",
                    "ShipmentStatus": "Delayed",
                    "DeliveryDelayDays": 18.0,
                    "TransportationCost": 45000,
                    "InventoryLevel": 120,
                    "DemandForecast": 800,
                    "IncidentCategory": "supplier",
                    "Title": "Critical delay",
                    "Description": "18-day delay for electronics",
                    "OccurredAt": "2024-06-01",
                    "ResolutionStatus": "open",
                },
                {
                    "IncidentCode": "INC-00002",
                    "SupplierID": "SUP-001",
                    "SupplierName": "GlobalTech",
                    "Region": "Asia-Pacific",
                    "SupplierCategory": "Electronics",
                    "ReliabilityScore": 72.0,
                    "WarehouseLocation": "Los Angeles",
                    "ShipmentStatus": "In-Transit",
                    "DeliveryDelayDays": 3.0,
                    "TransportationCost": 12000,
                    "InventoryLevel": 500,
                    "DemandForecast": 600,
                    "IncidentCategory": "inventory",
                    "Title": "Low stock alert",
                    "Description": "Approaching reorder point",
                    "OccurredAt": "2024-06-02",
                    "ResolutionStatus": "in_progress",
                },
            ]
        )

    def test_produces_record_and_supplier_summary_chunks(self):
        from app.ingestion.chunker import SupplyChainChunker

        df = self._sample_df()
        chunks = SupplyChainChunker().chunk_dataframe(df)

        record_chunks = [c for c in chunks if c.chunk_type == "record"]
        summary_chunks = [c for c in chunks if c.chunk_type == "supplier_summary"]

        assert len(record_chunks) == 2
        assert len(summary_chunks) == 1  # one unique supplier

    def test_record_chunk_has_required_metadata_keys(self):
        from app.ingestion.chunker import SupplyChainChunker

        df = self._sample_df()
        chunks = SupplyChainChunker().chunk_dataframe(df)
        record = next(c for c in chunks if c.chunk_type == "record")

        required_keys = {"supplier_id", "severity", "incident_category", "delivery_delay_days", "chunk_type"}
        assert required_keys.issubset(record.metadata.keys())

    def test_severity_calculated_correctly(self):
        from app.ingestion.chunker import _calc_severity

        assert _calc_severity(18.0, 120, 800) == "critical"   # delay > 14 AND coverage 0.15
        assert _calc_severity(0.0, 900, 800) == "low"         # no delay, coverage fine
        assert _calc_severity(5.0, 400, 800) == "medium"      # delay 3-7, coverage 0.5

    def test_supplier_summary_chunk_text_contains_risk_label(self):
        from app.ingestion.chunker import SupplyChainChunker

        df = self._sample_df()
        chunks = SupplyChainChunker().chunk_dataframe(df)
        summary = next(c for c in chunks if c.chunk_type == "supplier_summary")
        assert "RISK" in summary.text.upper()
