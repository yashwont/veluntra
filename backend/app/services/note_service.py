import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.note import Note
from app.repositories.notes import NoteRepository
from app.schemas.note import NoteCreate, NoteUpdate

logger = logging.getLogger(__name__)


class NoteNotFoundError(NotFoundError):
    code = "NOTE_NOT_FOUND"
    message = "The requested note does not exist."


class NoteService:
    """Business logic for notes within one workspace.

    The caller must already have verified the user belongs to `workspace_id`.
    """

    def __init__(self, session: AsyncSession, workspace_id: uuid.UUID) -> None:
        self.session = session
        self.workspace_id = workspace_id
        self.notes = NoteRepository(session)

    async def create(self, data: NoteCreate) -> Note:
        note = Note(
            workspace_id=self.workspace_id,
            title=data.title,
            content=data.content,
            tags=data.tags,
        )
        self.notes.add(note)
        await self.session.commit()
        await self.session.refresh(note)  # load server-generated columns
        logger.info(
            "note created",
            extra={"note_id": str(note.id), "workspace_id": str(self.workspace_id)},
        )
        return note

    async def get(self, note_id: uuid.UUID) -> Note:
        note = await self.notes.get(self.workspace_id, note_id)
        if note is None:
            raise NoteNotFoundError()
        return note

    async def list(
        self, *, query: str | None, tags: list[str], limit: int, offset: int
    ) -> tuple[list[tuple[Note, str]], int]:
        return await self.notes.list(
            self.workspace_id, query=query, tags=tags, limit=limit, offset=offset
        )

    async def update(self, note_id: uuid.UUID, data: NoteUpdate) -> Note:
        note = await self.get(note_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(note, field, value)
        await self.session.commit()
        await self.session.refresh(note)
        return note

    async def delete(self, note_id: uuid.UUID) -> None:
        note = await self.get(note_id)
        await self.notes.delete(note)
        await self.session.commit()
        logger.info(
            "note deleted",
            extra={"note_id": str(note_id), "workspace_id": str(self.workspace_id)},
        )
