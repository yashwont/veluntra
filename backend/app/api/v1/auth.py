from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(session)


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(
    body: RegisterRequest, service: AuthService = Depends(get_auth_service)
) -> UserRead:
    """Creates the user and a personal workspace they own. Log in afterwards."""
    user = await service.register(body.email, body.password, body.full_name)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair, summary="Log in")
async def login(
    body: LoginRequest, service: AuthService = Depends(get_auth_service)
) -> TokenPair:
    """Returns a short-lived access token and a long-lived refresh token."""
    return await service.login(body.email, body.password)


@router.post("/refresh", response_model=TokenPair, summary="Refresh tokens")
async def refresh(
    body: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> TokenPair:
    """Rotates the refresh token: the one sent is revoked and a new pair returned."""
    return await service.refresh(body.refresh_token)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out"
)
async def logout(
    body: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> Response:
    """Revokes the given refresh token."""
    await service.logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
