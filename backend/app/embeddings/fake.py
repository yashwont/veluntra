import hashlib
import math
import re
from collections.abc import Sequence

from app.embeddings.types import EMBEDDING_DIMENSIONS

_WORD = re.compile(r"[a-z0-9]+")


class FakeEmbeddingProvider:
    """Deterministic, offline stand-in for a real embedding model.

    Hashes each word into one of the vector's dimensions (a "hashing trick" bag of
    words), so texts sharing words get similar vectors. It captures word overlap,
    not meaning: "car" and "automobile" are unrelated. Enough to exercise the whole
    pipeline; swap in a real provider for true semantic search.
    """

    name = "fake"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for word in _WORD.findall(text.lower()):
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest, "big") % EMBEDDING_DIMENSIONS] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            # No words: a fixed unit vector keeps cosine distance well defined
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]
