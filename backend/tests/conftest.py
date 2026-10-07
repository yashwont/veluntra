import os

# Tests run against a separate database so they never touch development data.
# This must be set before the app (and its settings) are imported.
TEST_DB = "veluntra_test"
os.environ["POSTGRES_DB"] = TEST_DB
# Tests must never reach a real (paid) model, whatever the developer's .env says
os.environ["LLM_PROVIDER"] = "fake"
os.environ["EMBEDDING_PROVIDER"] = "fake"
# Uploaded files go to a throwaway directory, never the developer's real storage
import tempfile  # noqa: E402

os.environ["DOCUMENT_STORAGE_DIR"] = tempfile.mkdtemp(prefix="veluntra_test_docs_")

import subprocess  # noqa: E402
import sys  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.llm.factory import get_llm_provider  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
async def _database() -> AsyncIterator[None]:
    """Create the test database if needed and bring it to the latest migration."""
    s = get_settings()
    conn = await asyncpg.connect(
        user=s.postgres_user,
        password=s.postgres_password,
        host=s.postgres_host,
        port=s.postgres_port,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()

    # Run the real migrations (in a subprocess: Alembic's env.py starts its own loop)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
    )
    yield
    await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE refresh_tokens, workspace_members, workspaces, users CASCADE"
            )
        )


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client that calls the FastAPI app in-process (no network)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def use_provider():
    """Replace the LLM provider for one test: use_provider(ScriptedProvider(...))."""

    def _use(provider):
        app.dependency_overrides[get_llm_provider] = lambda: provider
        return provider

    yield _use
    app.dependency_overrides.pop(get_llm_provider, None)


PASSWORD = "a-long-test-password"


@dataclass
class TestUser:
    __test__ = False  # not a pytest test class

    email: str
    user_id: str
    workspace_id: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


@pytest.fixture
def make_user(client: AsyncClient):
    """Factory: register + log in a user, returning their ids and tokens."""

    async def _make(email: str = "alice@example.com", name: str = "Alice") -> TestUser:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD, "full_name": name},
        )
        assert reg.status_code == 201, reg.text
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        tokens = login.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        workspaces = (await client.get("/api/v1/workspaces", headers=headers)).json()
        return TestUser(
            email=email,
            user_id=reg.json()["id"],
            workspace_id=workspaces[0]["id"],
            access_token=tokens["access_token"],
            refresh_token=tokens["refresh_token"],
        )

    return _make
