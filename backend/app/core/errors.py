import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, client-facing errors.

    Services raise subclasses (e.g. TaskNotFoundError); the handler below
    turns them into the standard error response. Never put internal details
    (SQL, stack traces, file paths) in `message`.
    """

    status_code: int = 400
    code: str = "BAD_REQUEST"
    message: str = "The request could not be processed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "The requested resource does not exist."


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "The request conflicts with the current state of the resource."


class AuthenticationError(AppError):
    status_code = 401
    code = "NOT_AUTHENTICATED"
    message = "Authentication is required or the credentials are invalid."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action."


def error_response(
    status_code: int, code: str, message: str, details: object | None = None
) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Covers framework errors such as unknown routes (404) and 405
    phrase = HTTPStatus(exc.status_code).phrase
    code = phrase.upper().replace(" ", "_").replace("'", "")
    return error_response(exc.status_code, code, str(exc.detail))


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(
        422, "VALIDATION_ERROR", "The request data is invalid.", details
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to the logs only, never to the client
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={"method": request.method, "path": request.url.path},
    )
    return error_response(
        500, "INTERNAL_ERROR", "An unexpected error occurred."
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
