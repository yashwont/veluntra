import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message


class ConversationRepository:
    """Conversation access. Every lookup is scoped by workspace AND user: a
    conversation is private to the person who started it."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, conversation: Conversation) -> None:
        self.session.add(conversation)

    def add_message(self, message: Message) -> None:
        self.session.add(message)

    async def get(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation | None:
        result = await self.session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
                Conversation.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Conversation], int]:
        conditions = [Conversation.workspace_id == workspace_id, Conversation.user_id == user_id]
        total = await self.session.scalar(
            select(func.count()).select_from(Conversation).where(*conditions)
        )
        result = await self.session.execute(
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars()), total or 0

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        """The newest `limit` messages, oldest first."""
        if limit <= 0:
            return []
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(result.scalars())))

    async def all_messages(self, conversation_id: uuid.UUID, limit: int = 500) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .limit(limit)
        )
        return list(result.scalars())

    async def delete(self, conversation: Conversation) -> None:
        await self.session.delete(conversation)
