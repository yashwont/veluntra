import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.workspace import WorkspaceRole


class WorkspaceRead(BaseModel):
    id: uuid.UUID
    name: str
    role: WorkspaceRole = Field(description="The current user's role in this workspace.")
    created_at: datetime
