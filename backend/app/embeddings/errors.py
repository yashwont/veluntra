from app.core.errors import AppError


class EmbeddingError(AppError):
    """The embedding service failed. The message is safe to show: it says what is wrong
    without including any of the text being embedded."""

    status_code = 502
    code = "EMBEDDINGS_UNAVAILABLE"
    message = "The search embedding service is temporarily unavailable."
