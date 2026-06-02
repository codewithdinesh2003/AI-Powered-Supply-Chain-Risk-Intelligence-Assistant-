from __future__ import annotations

import asyncio
import logging
from typing import List

from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100  # OpenAI recommends ≤ 2048 inputs, 100 is safe for large texts


class OpenAIEmbedder:
    """Generates embeddings via OpenAI text-embedding-3-small in async batches."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, returning a parallel list of embedding vectors."""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        batches = [texts[i : i + _BATCH_SIZE] for i in range(0, len(texts), _BATCH_SIZE)]

        logger.info("Generating embeddings — %d texts / %d batches.", len(texts), len(batches))

        for batch_idx, batch in enumerate(batches, 1):
            embeddings = await self._embed_batch(batch)
            all_embeddings.extend(embeddings)
            logger.info("  Batch %d/%d complete (%d vectors).", batch_idx, len(batches), len(embeddings))

            # Polite pause between batches to avoid rate-limit bursts
            if batch_idx < len(batches):
                await asyncio.sleep(0.5)

        return all_embeddings

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Truncate texts that are too long (token limit safety)
        truncated = [t[:25_000] for t in texts]

        response = await self._client.embeddings.create(
            model=self._model,
            input=truncated,
        )
        # response.data is sorted by index
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    async def embed_query(self, query: str) -> List[float]:
        """Single-query embedding used at retrieval time."""
        results = await self.embed_texts([query])
        return results[0]
