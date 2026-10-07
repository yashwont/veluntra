import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_workspace_membership
from app.core.config import get_settings
from app.db.session import get_session
from app.models.document import DocumentStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.common import Page
from app.schemas.document import DocumentRead, DocumentSearchHit
from app.services.document_processing import process_document
from app.services.document_service import DocumentService, UploadTooLargeError

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])


async def get_document_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> DocumentService:
    """Builds a DocumentService bound to the workspace, after authorizing access."""
    return DocumentService(session, workspace_id)


@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document",
)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(description="TXT, MD, PDF or DOCX."),
    user: User = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentRead:
    """Stores the file and returns immediately with status `pending`. Text
    extraction, chunking and embedding run in the background; poll the document
    until its status is `ready` (searchable) or `failed`."""
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # never buffer more than one byte over the limit
    if len(data) > limit:
        raise UploadTooLargeError(
            f"The file is too large. The maximum size is {limit // (1024 * 1024)} MB."
        )
    document = await service.upload(filename=file.filename, data=data, user_id=user.id)
    background.add_task(process_document, document.id)
    return DocumentRead.model_validate(document)


@router.get("", response_model=Page[DocumentRead], summary="List documents")
async def list_documents(
    status_filter: DocumentStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: DocumentService = Depends(get_document_service),
) -> Page[DocumentRead]:
    rows, total = await service.list(status=status_filter, limit=limit, offset=offset)
    return Page[DocumentRead](
        items=[DocumentRead.model_validate(d) for d in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# Declared before "/{document_id}" so "search" is not parsed as an id
@router.get(
    "/search", response_model=list[DocumentSearchHit], summary="Search document contents"
)
async def search_documents(
    q: str = Query(..., min_length=1, max_length=500, description="What to look for."),
    limit: int = Query(5, ge=1, le=20),
    service: DocumentService = Depends(get_document_service),
) -> list[DocumentSearchHit]:
    """Semantic search: returns the passages (chunks) closest to the query, best
    first. Only documents with status `ready` are searched."""
    hits = await service.search(q, limit=limit)
    return [
        DocumentSearchHit(
            document_id=h.document_id,
            filename=h.filename,
            chunk_index=h.chunk_index,
            content=h.content,
            score=h.score,
        )
        for h in hits
    ]


@router.get("/{document_id}", response_model=DocumentRead, summary="Get a document")
async def get_document(
    document_id: uuid.UUID, service: DocumentService = Depends(get_document_service)
) -> DocumentRead:
    return DocumentRead.model_validate(await service.get(document_id))


@router.get("/{document_id}/download", summary="Download the original file")
async def download_document(
    document_id: uuid.UUID, service: DocumentService = Depends(get_document_service)
) -> FileResponse:
    document = await service.get(document_id)
    return FileResponse(
        service.storage.path_of(document.storage_key),
        media_type=document.content_type,
        filename=document.filename,
        content_disposition_type="attachment",  # never rendered inline in our origin
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/{document_id}/reprocess",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Process a document again",
)
async def reprocess_document(
    document_id: uuid.UUID,
    background: BackgroundTasks,
    service: DocumentService = Depends(get_document_service),
) -> DocumentRead:
    """Retry after a failure, or re-index. 409 while it is already being processed."""
    document = await service.reset_for_reprocessing(document_id)
    background.add_task(process_document, document.id)
    return DocumentRead.model_validate(document)


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and its file",
)
async def delete_document(
    document_id: uuid.UUID, service: DocumentService = Depends(get_document_service)
) -> Response:
    await service.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
