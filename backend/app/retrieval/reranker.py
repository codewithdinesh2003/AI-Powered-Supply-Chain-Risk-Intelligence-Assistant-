from __future__ import annotations

import logging
import threading
from typing import List, Optional

from app.config import get_settings
from app.retrieval.vector_store import RetrievedDocument

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model_singleton: Optional[object] = None


def _get_model():
    """Lazy-load the CrossEncoder model — ~2 s first call, instant thereafter."""
    global _model_singleton
    if _model_singleton is None:
        with _lock:
            if _model_singleton is None:
                from sentence_transformers import CrossEncoder

                model_name = get_settings().reranker_model
                logger.info("Loading CrossEncoder reranker: %s …", model_name)
                _model_singleton = CrossEncoder(model_name)
                logger.info("CrossEncoder ready.")
    return _model_singleton


class CrossEncoderReranker:
    """Re-scores a candidate list using a cross-encoder model.

    The cross-encoder sees both the query and the document simultaneously,
    giving much higher precision than bi-encoder cosine similarity alone.
    Typical latency: ~50–200 ms for 20 candidates on CPU.
    """

    def rerank(
        self,
        query: str,
        candidates: List[RetrievedDocument],
        top_k: int = 10,
    ) -> List[RetrievedDocument]:
        if not candidates:
            return []

        model = _get_model()

        # CrossEncoder expects (query, passage) pairs
        pairs = [(query, doc.text[:2000]) for doc in candidates]  # cap at 2000 chars
        scores: List[float] = model.predict(pairs).tolist()

        # Attach cross-encoder scores and sort
        for doc, score in zip(candidates, scores):
            doc.score = float(score)

        reranked = sorted(candidates, key=lambda d: d.score, reverse=True)

        # Re-assign ranks after reranking
        for rank, doc in enumerate(reranked):
            doc.rank = rank

        return reranked[:top_k]
