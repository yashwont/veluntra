from functools import lru_cache

from app.core.config import get_settings
from app.llm.fake import FakeProvider
from app.llm.types import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """The configured model provider (LLM_PROVIDER). Used as a FastAPI dependency,
    so tests can substitute their own."""
    provider = get_settings().llm_provider.lower()
    if provider == "fake":
        return FakeProvider()
    # "anthropic" is added together with the real adapter
    raise RuntimeError(f"Unknown LLM_PROVIDER '{provider}'. Supported: fake.")
