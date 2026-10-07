"""Provider-neutral interface for turning text into vectors.

Every vector has exactly EMBEDDING_DIMENSIONS numbers: that width is baked into
the database column, so a provider whose model produces another size must
project or truncate to it (or the column must be migrated).
"""

from collections.abc import Sequence
from typing import Protocol

EMBEDDING_DIMENSIONS = 384


class EmbeddingProvider(Protocol):
    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One unit-length vector per input text, in order."""
        ...
