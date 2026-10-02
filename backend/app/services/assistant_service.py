import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import Orchestrator
from app.agents.prompts import build_system_prompt
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.llm.errors import LLMError
from app.llm.types import LLMProvider, TextTurn
from app.models.conversation import Conversation, Message, MessageRole
from app.models.user import User
from app.repositories.conversations import ConversationRepository
from app.tools import default_registry
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ConversationNotFoundError(NotFoundError):
    code = "CONVERSATION_NOT_FOUND"
    message = "The requested conversation does not exist."


class AssistantUnavailableError(AppError):
    status_code = 502
    code = "ASSISTANT_UNAVAILABLE"
    message = "The assistant is temporarily unavailable. Please try again."


def _title_from(message: str) -> str:
    one_line = " ".join(message.split())
    return one_line if len(one_line) <= 60 else one_line[:57] + "..."


def _build_turns(history: list[Message], new_message: str) -> list[TextTurn]:
    """Past messages plus the new one, as model input.

    - Only text is replayed. Tool call details stay in the database; the
      assistant's own reply already says what happened. This keeps context small
      and means stored data is never fed back as if it were fresh tool output.
    - Roles must start with 'user' and alternate, so leading assistant messages
      are dropped (the history window can cut mid-exchange) and consecutive
      same-role messages (e.g. after a failed request) are merged.
    """
    pairs = [(m.role.value, m.content) for m in history] + [("user", new_message)]
    turns: list[TextTurn] = []
    for role, text in pairs:
        if not turns and role != "user":
            continue
        if turns and turns[-1].role == role:
            turns[-1] = TextTurn(turns[-1].role, f"{turns[-1].text}\n\n{text}")
        else:
            turns.append(TextTurn("user" if role == "user" else "assistant", text))
    return turns


class AssistantService:
    """Conversations with the assistant, inside one workspace, for one user.

    The caller must already have verified the user belongs to `workspace_id`.
    """

    def __init__(
        self,
        session: AsyncSession,
        user: User,
        workspace_id: uuid.UUID,
        provider: LLMProvider,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.workspace_id = workspace_id
        self.provider = provider
        self.registry = registry or default_registry()
        self.conversations = ConversationRepository(session)

    async def chat(
        self, message: str, conversation_id: uuid.UUID | None, timezone_name: str
    ) -> tuple[Conversation, Message]:
        settings = get_settings()
        tz = ZoneInfo(timezone_name)

        recent: list[Message] = []
        if conversation_id is not None:
            conversation = await self._get(conversation_id)
            recent = await self.conversations.recent_messages(
                conversation.id, settings.assistant_history_messages
            )
        else:
            conversation = Conversation(
                workspace_id=self.workspace_id,
                user_id=self.user.id,
                title=_title_from(message),
            )
            self.conversations.add(conversation)
            await self.session.flush()

        # Save the user's message first so it is never lost if the model call fails
        self.conversations.add_message(
            Message(conversation_id=conversation.id, role=MessageRole.USER, content=message)
        )
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.commit()

        orchestrator = Orchestrator(self.provider, self.registry, settings.assistant_max_iterations)
        ctx = ToolContext(
            session=self.session,
            workspace_id=self.workspace_id,
            user_id=self.user.id,
            timezone=tz,
        )
        try:
            result = await orchestrator.run(
                system=build_system_prompt(datetime.now(tz)),
                turns=_build_turns(recent, message),
                ctx=ctx,
            )
        except LLMError:
            logger.exception(
                "assistant provider failed",
                extra={"provider": self.provider.name, "workspace_id": str(self.workspace_id)},
            )
            raise AssistantUnavailableError() from None

        reply = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=result.text,
            tool_events=[asdict(e) for e in result.tool_events],
            provider=self.provider.name,
            input_tokens=result.input_tokens or None,
            output_tokens=result.output_tokens or None,
        )
        self.conversations.add_message(reply)
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(reply)
        logger.info(
            "assistant replied",
            extra={
                "conversation_id": str(conversation.id),
                "stop_reason": result.stop_reason,
                "tools": [e.name for e in result.tool_events],
            },
        )
        return conversation, reply

    async def list_conversations(
        self, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        return await self.conversations.list_for_user(self.workspace_id, self.user.id, limit, offset)

    async def get_conversation(self, conversation_id: uuid.UUID) -> tuple[Conversation, list[Message]]:
        conversation = await self._get(conversation_id)
        return conversation, await self.conversations.all_messages(conversation.id)

    async def delete_conversation(self, conversation_id: uuid.UUID) -> None:
        conversation = await self._get(conversation_id)
        await self.conversations.delete(conversation)
        await self.session.commit()

    async def _get(self, conversation_id: uuid.UUID) -> Conversation:
        conversation = await self.conversations.get(
            self.workspace_id, self.user.id, conversation_id
        )
        if conversation is None:
            raise ConversationNotFoundError()
        return conversation
