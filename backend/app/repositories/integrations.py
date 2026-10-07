from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import IntegrationAccount, IntegrationProvider


class IntegrationRepository:
    """Connections are personal: every method filters on both workspace and user."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, account: IntegrationAccount) -> None:
        self.session.add(account)

    async def get(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, account_id: uuid.UUID
    ) -> IntegrationAccount | None:
        result = await self.session.execute(
            select(IntegrationAccount).where(
                IntegrationAccount.id == account_id,
                IntegrationAccount.workspace_id == workspace_id,
                IntegrationAccount.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_provider(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID, provider: IntegrationProvider
    ) -> IntegrationAccount | None:
        result = await self.session.execute(
            select(IntegrationAccount).where(
                IntegrationAccount.workspace_id == workspace_id,
                IntegrationAccount.user_id == user_id,
                IntegrationAccount.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[IntegrationAccount]:
        result = await self.session.execute(
            select(IntegrationAccount)
            .where(
                IntegrationAccount.workspace_id == workspace_id,
                IntegrationAccount.user_id == user_id,
            )
            .order_by(IntegrationAccount.created_at)
        )
        return list(result.scalars())

    async def delete(self, account: IntegrationAccount) -> None:
        await self.session.delete(account)
