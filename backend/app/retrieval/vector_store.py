from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings
from app.ingestion.chunker import DocumentChunk

logger = logging.getLogger(__name__)


class RetrievedDocument:
    """Unified result object returned by retrieval methods."""

    __slots__ = ("doc_id", "text", "metadata", "score", "rank")

    def __init__(
        self,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
        score: float = 0.0,
        rank: int = 0,
    ) -> None:
        self.doc_id = doc_id
        self.text = text
        self.metadata = metadata
        self.score = score
        self.rank = rank

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "text": self.text,
            "metadata": self.metadata,
            "score": self.score,
            "rank": self.rank,
        }


_store_singleton: "ChromaVectorStore | None" = None


def get_vector_store() -> "ChromaVectorStore":
    """Return the module-level singleton — creates it on first call."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = ChromaVectorStore()
    return _store_singleton


class ChromaVectorStore:
    """Wraps ChromaDB for persistent supply-chain document storage and search."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection '%s' ready (%d documents).",
            settings.chroma_collection_name,
            self._collection.count(),
        )

    # ── Write ─────────────────────────────────────────────────────────────

    def add_documents(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
        batch_size: int = 200,
    ) -> None:
        """Upsert chunks + pre-computed embeddings into ChromaDB."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length.")

        total = len(chunks)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch_chunks = chunks[start:end]
            batch_embeddings = embeddings[start:end]

            self._collection.upsert(
                ids=[c.chunk_id for c in batch_chunks],
                documents=[c.text for c in batch_chunks],
                embeddings=batch_embeddings,
                metadatas=[c.metadata for c in batch_chunks],
            )
            logger.info(
                "ChromaDB upsert: %d/%d documents.", end, total
            )

    def delete_collection(self) -> None:
        settings = get_settings()
        self._client.delete_collection(settings.chroma_collection_name)
        logger.warning("ChromaDB collection deleted.")

    # ── Read ──────────────────────────────────────────────────────────────

    async def search(
        self,
        query_embedding: List[float],
        k: int = 15,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedDocument]:
        """Semantic similarity search using pre-computed query embedding."""
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(k, max(self._collection.count(), 1)),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        docs: List[RetrievedDocument] = []
        if not results["ids"] or not results["ids"][0]:
            return docs

        for rank, (doc_id, text, meta, dist) in enumerate(
            zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ):
            # ChromaDB cosine distance → similarity score (1 - distance)
            score = float(1.0 - dist)
            docs.append(
                RetrievedDocument(
                    doc_id=doc_id,
                    text=text,
                    metadata=meta,
                    score=score,
                    rank=rank,
                )
            )

        return docs

    def count(self) -> int:
        return self._collection.count()

    def get_all_texts(self) -> List[str]:
        """Return all stored document texts (used to rebuild BM25 index)."""
        result = self._collection.get(include=["documents"])
        return result["documents"] or []

    def get_all_with_metadata(self) -> tuple[List[str], List[str], List[Dict]]:
        """Return (ids, texts, metadatas) for all stored documents."""
        result = self._collection.get(include=["documents", "metadatas"])
        return (
            result.get("ids", []),
            result.get("documents", []),
            result.get("metadatas", []),
        )
