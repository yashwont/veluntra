from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard paginated list response."""

    items: list[T]
    total: int = Field(description="Total matching items across all pages.")
    limit: int
    offset: int
