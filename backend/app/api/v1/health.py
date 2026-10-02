import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    database: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    responses={503: {"model": HealthResponse, "description": "Database unreachable"}},
)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse | JSONResponse:
    """Returns 200 if the API is running and the database is reachable."""
    settings = get_settings()
    try:
        await session.execute(text("SELECT 1"))
        db_status, http_status = "ok", 200
    except (SQLAlchemyError, OSError):  # OSError: connection refused / DNS failure
        logger.exception("Health check: database unreachable")
        db_status, http_status = "unavailable", 503

    body = HealthResponse(
        status="ok" if http_status == 200 else "degraded",
        app=settings.app_name,
        environment=settings.environment,
        database=db_status,
    )
    if http_status == 200:
        return body
    return JSONResponse(status_code=http_status, content=body.model_dump())
