import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error: str | None = Field(description="Why processing failed, when status is 'failed'.")
    chunk_count: int
    created_at: datetime
    processed_at: datetime | None


class DocumentSearchHit(BaseModel):
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str = Field(description="The matching passage.")
    score: float = Field(description="Cosine similarity to the query; higher is closer.")
