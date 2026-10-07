import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_workspace_membership
from app.db.session import get_session
from app.integrations.google.factory import get_google_api
from app.integrations.google.types import GoogleApi
from app.llm.factory import get_llm_provider
from app.llm.types import LLMProvider
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.schemas.assistant import (
    AssistantStatus,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationRead,
    MessageRead,
)
from app.schemas.common import Page
from app.services.assistant_service import AssistantService

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["assistant"])


async def get_assistant_service(
    workspace_id: uuid.UUID,
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    provider: LLMProvider = Depends(get_llm_provider),
    google: GoogleApi = Depends(get_google_api),
) -> AssistantService:
    """Builds the service for this workspace, after authorizing access."""
    return AssistantService(session, user, workspace_id, provider, google=google)


@router.get("/assistant/status", response_model=AssistantStatus, summary="Which model is answering")
async def assistant_status(
    _membership: WorkspaceMember = Depends(get_workspace_membership),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AssistantStatus:
    return AssistantStatus(provider=provider.name, demo=provider.name == "fake")


@router.post("/assistant/chat", response_model=ChatResponse, summary="Chat with the assistant")
async def chat(
    body: ChatRequest, service: AssistantService = Depends(get_assistant_service)
) -> ChatResponse:
    """Send a message. The assistant may create or search tasks and notes on your
    behalf; the `tool_events` on its reply list exactly what it did."""
    conversation, reply = await service.chat(body.message, body.conversation_id, body.timezone)
    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageRead.model_validate(reply),
        provider=service.provider.name,
    )


@router.get("/conversations", response_model=Page[ConversationRead], summary="List my conversations")
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: AssistantService = Depends(get_assistant_service),
) -> Page[ConversationRead]:
    """Your own conversations in this workspace, most recently active first."""
    items, total = await service.list_conversations(limit, offset)
    return Page[ConversationRead](
        items=[ConversationRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get a conversation with its messages",
)
async def get_conversation(
    conversation_id: uuid.UUID, service: AssistantService = Depends(get_assistant_service)
) -> ConversationDetail:
    conversation, messages = await service.get_conversation(conversation_id)
    return ConversationDetail(
        **ConversationRead.model_validate(conversation).model_dump(),
        messages=[MessageRead.model_validate(m) for m in messages],
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation",
)
async def delete_conversation(
    conversation_id: uuid.UUID, service: AssistantService = Depends(get_assistant_service)
) -> Response:
    await service.delete_conversation(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
