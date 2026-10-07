from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Application settings, loaded from environment variables.

    Docker Compose injects the values from .env into the container,
    so no .env file is read here. Missing required values fail at startup.
    """

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_name: str = "Veluntra"
    environment: str = "development"
    log_level: str = "INFO"

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # AI assistant. "fake" is a rule-based demo model that needs no API key.
    llm_provider: str = "fake"
    assistant_max_iterations: int = Field(default=5, ge=1, le=10)
    # Only this many recent messages are sent to the model, never the whole history
    assistant_history_messages: int = Field(default=12, ge=0, le=50)

    # Documents. Files live on local disk under this directory (never inside the
    # web root); the database stores only an opaque key.
    document_storage_dir: str = "storage/documents"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    # "fake" = deterministic offline embeddings, good enough to develop and test
    # the pipeline. A real provider is added together with its adapter.
    embedding_provider: str = "fake"

    # Google integrations (Gmail, Calendar, Drive: read-only). Create an OAuth client in
    # Google Cloud Console (see docs/GOOGLE_SETUP.md); without these, connecting is
    # simply unavailable.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Where this API is reachable from the user's browser: Google redirects back to
    # {public_backend_url}/api/v1/integrations/google/callback
    public_backend_url: str = "http://localhost:8000"
    # Where the user is sent after connecting
    frontend_url: str = "http://localhost:3000"
    # Fernet key for encrypting stored OAuth tokens. Optional: derived from SECRET_KEY
    # when empty (generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    integration_encryption_key: str = ""

    @property
    def google_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def database_url(self) -> URL:
        # URL.create escapes special characters in the password safely
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
