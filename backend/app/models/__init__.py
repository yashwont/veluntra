# Import every model here so Alembic autogenerate and Base.metadata see them all.
from app.models.refresh_token import RefreshToken
from app.models.conversation import Conversation, Message, MessageRole
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.memory import Memory, MemoryKind, MemorySource
from app.models.note import Note
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceRole

__all__ = [
    "Conversation",
    "Message",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "Memory",
    "MemoryKind",
    "MemorySource",
    "MessageRole",
    "Note",
    "RefreshToken",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "User",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
]
