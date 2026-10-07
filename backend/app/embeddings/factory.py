from functools import lru_cache

from app.core.config import get_settings
from app.embeddings.fake import FakeEmbeddingProvider
from app.embeddings.types import EmbeddingProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    """The configured embedding provider (EMBEDDING_PROVIDER)."""
    provider = get_settings().embedding_provider.lower()
    if provider == "fake":
        return FakeEmbeddingProvider()
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER '{provider}'. Supported: fake.")
