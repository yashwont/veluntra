import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, NotFoundError
from app.core.security import decode_token
from app.db.session import get_session
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.repositories.users import UserRepository
from app.repositories.workspaces import WorkspaceRepository

# auto_error=False so a missing header goes through our standard error format
bearer_scheme = HTTPBearer(auto_error=False)


class WorkspaceNotFoundError(NotFoundError):
    code = "WORKSPACE_NOT_FOUND"
    message = "The requested workspace does not exist."


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Authenticate the request from its access token."""
    if credentials is None:
        raise AuthenticationError("Authentication is required.")

    claims = decode_token(credentials.credentials, "access")
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError:
        raise AuthenticationError("Invalid or expired token.") from None

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired token.")
    return user


async def get_workspace_membership(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMember:
    """Authorize access to a workspace (path parameter `workspace_id`).

    Every route that touches workspace data must depend on this. Non-members get
    404, not 403, so workspace ids can't be probed.
    """
    membership = await WorkspaceRepository(session).get_membership(
        workspace_id, user.id
    )
    if membership is None:
        raise WorkspaceNotFoundError()
    return membership
