"""Real, free embeddings from a local Ollama model (EMBEDDING_PROVIDER=ollama).

Unlike the demo embedder, these capture meaning: "car" finds "automobile". The database
column holds exactly EMBEDDING_DIMENSIONS numbers per vector, so the model must produce
that width: `all-minilm` does (384). A model with a different width is refused with a
clear message rather than being silently truncated.
"""

import logging
import math
from collections.abc import Sequence

import httpx

from app.core.config import get_settings
from app.embeddings.errors import EmbeddingError
from app.embeddings.types import EMBEDDING_DIMENSIONS
from app.integrations.ollama import OllamaClient, OllamaError

logger = logging.getLogger(__name__)

BATCH_SIZE = 32


class OllamaEmbeddingProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.model = model or settings.ollama_embedding_model
        self.client = OllamaClient(
            base_url or settings.ollama_base_url,
            timeout or settings.ollama_timeout_seconds,
            transport,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            vectors.extend(await self._embed_batch(list(texts[start : start + BATCH_SIZE])))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            data = await self.client.post(
                "/api/embed", {"model": self.model, "input": batch}, model=self.model
            )
        except OllamaError as exc:
            logger.error("ollama embedding failed", extra={"reason": str(exc), "model": self.model})
            raise EmbeddingError(str(exc)) from exc

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(batch):
            raise EmbeddingError("Ollama returned the wrong number of embeddings.")
        return [self._unit_vector(vector) for vector in embeddings]

    def _unit_vector(self, vector: object) -> list[float]:
        if not isinstance(vector, list) or not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in vector
        ):
            raise EmbeddingError("Ollama returned an invalid embedding.")
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise EmbeddingError(
                f"The embedding model '{self.model}' produces {len(vector)}-number vectors, but "
                f"this app stores {EMBEDDING_DIMENSIONS}. Use OLLAMA_EMBEDDING_MODEL=all-minilm."
            )
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else [float(x) for x in vector]
