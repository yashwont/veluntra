from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import AppError
from app.schemas.note import MAX_CONTENT_LENGTH, NoteCreate, normalize_tags
from app.services.note_service import NoteService
from app.tools.base import Tool, ToolContext


class CreateNoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    content: str = Field(default="", max_length=MAX_CONTENT_LENGTH)
    tags: list[str] = Field(default_factory=list, max_length=20, description="Short lowercase labels.")


class SearchNotesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Words to look for in note titles and content.",
    )
    tags: list[str] | None = Field(default=None, description="Only notes having all of these tags.")
    limit: int = Field(default=10, ge=1, le=25)


async def create_note(ctx: ToolContext, args: CreateNoteInput) -> dict[str, Any]:
    try:
        data = NoteCreate(title=args.title, content=args.content, tags=args.tags)
    except ValueError as exc:
        raise AppError(f"Invalid note: {exc}") from exc
    note = await NoteService(ctx.session, ctx.workspace_id).create(data)
    return {"note": {"id": str(note.id), "title": note.title, "tags": note.tags}}


async def search_notes(ctx: ToolContext, args: SearchNotesInput) -> dict[str, Any]:
    try:
        tags = normalize_tags(args.tags) if args.tags else []
    except ValueError as exc:
        raise AppError(f"Invalid tag filter: {exc}") from exc
    rows, total = await NoteService(ctx.session, ctx.workspace_id).list(
        query=args.query, tags=tags, limit=args.limit, offset=0
    )
    return {
        "total": total,
        "notes": [
            {"id": str(n.id), "title": n.title, "preview": preview, "tags": n.tags}
            for n, preview in rows
        ],
    }


NOTE_TOOLS = [
    Tool(
        name="create_note",
        description="Save a note for the user, with an optional list of tags.",
        input_model=CreateNoteInput,
        handler=create_note,
    ),
    Tool(
        name="search_notes",
        description=(
            "Search the user's notes by words (title and content) and/or tags. "
            "Results show a short preview of each note, not its full content."
        ),
        input_model=SearchNotesInput,
        handler=search_notes,
    ),
]
