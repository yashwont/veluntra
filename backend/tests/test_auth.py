from httpx import AsyncClient

from tests.conftest import PASSWORD


async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "Alice@Example.com", "password": PASSWORD, "full_name": "Alice"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "alice@example.com"  # normalized to lowercase
    assert "password" not in body and "password_hash" not in body


async def test_register_creates_personal_workspace_owned_by_user(make_user, client) -> None:
    user = await make_user()

    response = await client.get("/api/v1/workspaces", headers=user.headers)

    workspaces = response.json()
    assert len(workspaces) == 1
    assert workspaces[0]["role"] == "owner"


async def test_register_duplicate_email_is_rejected_case_insensitively(client: AsyncClient) -> None:
    payload = {"email": "bob@example.com", "password": PASSWORD, "full_name": "Bob"}
    await client.post("/api/v1/auth/register", json=payload)

    response = await client.post(
        "/api/v1/auth/register", json={**payload, "email": "BOB@example.com"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "c@example.com", "password": "short", "full_name": "C"},
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any(d["field"].endswith("password") for d in error["details"])


async def test_register_rejects_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": PASSWORD, "full_name": "C"},
    )

    assert response.status_code == 422


async def test_login_wrong_password_and_unknown_email_look_identical(make_user, client) -> None:
    user = await make_user()

    wrong_pw = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "wrong-password"}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )

    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
    assert wrong_pw.headers["www-authenticate"] == "Bearer"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_me_returns_current_user(make_user, client) -> None:
    user = await make_user()

    response = await client.get("/api/v1/users/me", headers=user.headers)

    assert response.status_code == 200
    assert response.json()["id"] == user.user_id


async def test_me_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not.a.token"}
    )

    assert response.status_code == 401


async def test_refresh_token_cannot_authenticate_requests(make_user, client) -> None:
    user = await make_user()

    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {user.refresh_token}"}
    )

    assert response.status_code == 401


async def test_refresh_rotates_tokens(make_user, client) -> None:
    user = await make_user()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user.refresh_token}
    )

    assert response.status_code == 200
    new = response.json()
    assert new["refresh_token"] != user.refresh_token
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {new['access_token']}"}
    )
    assert me.status_code == 200


async def test_reusing_rotated_refresh_token_revokes_all_sessions(make_user, client) -> None:
    user = await make_user()
    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user.refresh_token}
    )
    new_refresh = first.json()["refresh_token"]

    # The old token is replayed (e.g. by an attacker who stole it)
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user.refresh_token}
    )
    assert replay.status_code == 401

    # ...which also invalidates the legitimately issued new token
    after = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert after.status_code == 401


async def test_access_token_cannot_be_used_to_refresh(make_user, client) -> None:
    user = await make_user()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user.access_token}
    )

    assert response.status_code == 401


async def test_logout_revokes_refresh_token(make_user, client) -> None:
    user = await make_user()

    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": user.refresh_token}
    )
    refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user.refresh_token}
    )

    assert logout.status_code == 204
    assert refresh.status_code == 401
