from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.retrieval.vector_store import RetrievedDocument

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_INDEX_PATH = _DATA_DIR / "bm25_index.pkl"
_CORPUS_PATH = _DATA_DIR / "bm25_corpus.pkl"


def _tokenize(text: str) -> List[str]:
    """Must match the tokenizer used in pipeline.py when the index was built."""
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Retriever:
    """Keyword-based retrieval using a pre-built BM25Okapi index.

    The index is built by :mod:`app.ingestion.pipeline` and persisted to disk.
    Call :py:meth:`reload` after re-ingestion to pick up the new index without
    restarting the server.
    """

    def __init__(self) -> None:
        self._bm25: Any = None
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []
        self._loaded = False
        self._load()

    def _load(self) -> None:
        if not _INDEX_PATH.exists() or not _CORPUS_PATH.exists():
            logger.warning(
                "BM25 index not found at %s. "
                "Run scripts/ingest_data.py to build it. "
                "BM25 retrieval will return empty results until then.",
                _INDEX_PATH,
            )
            return

        try:
            with open(_INDEX_PATH, "rb") as f:
                self._bm25 = pickle.load(f)
            with open(_CORPUS_PATH, "rb") as f:
                corpus = pickle.load(f)
            self._ids = corpus["ids"]
            self._texts = corpus["texts"]
            self._metadatas = corpus["metadatas"]
            self._loaded = True
            logger.info("BM25 index loaded: %d documents.", len(self._ids))
        except Exception as exc:
            logger.error("Failed to load BM25 index: %s", exc)

    def reload(self) -> None:
        """Reload index from disk (call after fresh ingestion)."""
        self._loaded = False
        self._load()

    def search(self, query: str, k: int = 15) -> List[RetrievedDocument]:
        if not self._loaded or self._bm25 is None:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self._bm25.get_scores(tokens)

        # Build (score, index) pairs, sort descending, take top-k
        scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:k]

        results: List[RetrievedDocument] = []
        for rank, (idx, score) in enumerate(scored):
            if score <= 0:
                continue
            results.append(
                RetrievedDocument(
                    doc_id=self._ids[idx],
                    text=self._texts[idx],
                    metadata=self._metadatas[idx],
                    score=float(score),
                    rank=rank,
                )
            )

        return results

    @property
    def is_ready(self) -> bool:
        return self._loaded
