from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.ingestion.embedder import OpenAIEmbedder
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.vector_store import ChromaVectorStore, RetrievedDocument

logger = logging.getLogger(__name__)

# ── Filter conversion ────────────────────────────────────────────────────────

_CHROMA_FILTERABLE = {
    "supplier_id", "region", "supplier_category", "severity",
    "incident_category", "warehouse_location", "shipment_status",
    "chunk_type", "year", "month",
}


def _to_chroma_where(filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a simple flat filter dict into a ChromaDB ``where`` clause.

    Supported keys: supplier_id, severity, incident_category, warehouse_location,
    shipment_status, region, supplier_category, chunk_type, year, month.

    Example input : ``{"severity": "critical", "supplier_id": "SUP-002"}``
    Example output: ``{"$and": [{"severity": {"$eq": "critical"}}, ...]}``
    """
    if not filters:
        return None

    clauses = []
    for key, value in filters.items():
        if key not in _CHROMA_FILTERABLE or value is None:
            continue
        if isinstance(value, list):
            # e.g. severity: ["critical", "high"]  → $in
            clauses.append({key: {"$in": value}})
        else:
            clauses.append({key: {"$eq": value}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


# ── RRF fusion ────────────────────────────────────────────────────────────────

def _reciprocal_rank_fusion(
    result_lists: List[List[RetrievedDocument]],
    k: int = 60,
) -> List[RetrievedDocument]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion.

    RRF score: ``score(d) = Σ  1 / (k + rank(d))``
    Documents are de-duplicated by ``doc_id``.
    """
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, RetrievedDocument] = {}

    for result_list in result_lists:
        for rank, doc in enumerate(result_list, start=1):
            rrf_scores[doc.doc_id] = rrf_scores.get(doc.doc_id, 0.0) + 1.0 / (k + rank)
            if doc.doc_id not in doc_map:
                doc_map[doc.doc_id] = doc

    sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)

    fused: List[RetrievedDocument] = []
    for rank, doc_id in enumerate(sorted_ids):
        doc = doc_map[doc_id]
        doc.score = rrf_scores[doc_id]
        doc.rank = rank
        fused.append(doc)

    return fused


# ── Main hybrid retriever ────────────────────────────────────────────────────

class HybridRetriever:
    """Three-stage retrieval: semantic + BM25 → RRF fusion → CrossEncoder rerank.

    Architecture
    ============
    1. **Semantic search** (ChromaDB, cosine) — top ``semantic_k`` results
    2. **BM25 keyword search** — top ``bm25_k`` results
    3. **Reciprocal Rank Fusion** — de-duplicate and merge, score by RRF
    4. **CrossEncoder reranker** — precision boost on top ``rerank_pool`` candidates
    5. Return top ``top_k`` documents

    Filters
    =======
    Pass a flat dict of metadata filters; they are applied to the ChromaDB
    semantic search only (BM25 does not support metadata filtering).
    """

    def __init__(
        self,
        semantic_k: int = 15,
        bm25_k: int = 15,
        rerank_pool: int = 20,
    ) -> None:
        self._semantic_k = semantic_k
        self._bm25_k = bm25_k
        self._rerank_pool = rerank_pool

        self._vector_store = ChromaVectorStore()
        self._bm25 = BM25Retriever()
        self._reranker = CrossEncoderReranker()
        self._embedder = OpenAIEmbedder()

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedDocument]:
        """Full hybrid retrieval pipeline.

        Parameters
        ----------
        query:   Natural-language query from the user.
        top_k:   Number of documents to return after reranking.
        filters: Optional metadata filters (see :func:`_to_chroma_where`).
        """
        chroma_where = _to_chroma_where(filters or {})

        # ── Stage 1: parallel semantic + BM25 retrieval ───────────────────
        query_embedding = await self._embedder.embed_query(query)

        semantic_results = await self._vector_store.search(
            query_embedding=query_embedding,
            k=self._semantic_k,
            where=chroma_where,
        )
        logger.debug("Semantic search: %d results.", len(semantic_results))

        bm25_results = self._bm25.search(query, k=self._bm25_k)
        logger.debug("BM25 search: %d results.", len(bm25_results))

        # ── Stage 2: RRF fusion ───────────────────────────────────────────
        fused = _reciprocal_rank_fusion([semantic_results, bm25_results])
        logger.debug("After RRF fusion: %d unique documents.", len(fused))

        # ── Stage 3: CrossEncoder reranking ──────────────────────────────
        pool = fused[: self._rerank_pool]
        reranked = self._reranker.rerank(query, pool, top_k=top_k)
        logger.debug("After reranking: %d documents returned.", len(reranked))

        return reranked

    async def retrieve_for_agent(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        chunk_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convenience wrapper that returns a dict suitable for agent state.

        Automatically adds ``chunk_type`` filter when specified (e.g. agents
        that want supplier summaries only vs per-record chunks).
        """
        effective_filters = dict(filters or {})
        if chunk_type:
            effective_filters["chunk_type"] = chunk_type

        docs = await self.retrieve(query=query, top_k=top_k, filters=effective_filters)

        return {
            "documents": [d.to_dict() for d in docs],
            "scores": [d.score for d in docs],
            "query": query,
            "total_retrieved": len(docs),
        }

    def reload_bm25(self) -> None:
        """Reload BM25 index from disk after a new ingestion run."""
        self._bm25.reload()
        logger.info("BM25 index reloaded.")
