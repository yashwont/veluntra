import uuid

from httpx import AsyncClient


async def test_workspaces_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/workspaces")).status_code == 401
    assert (await client.get(f"/api/v1/workspaces/{uuid.uuid4()}")).status_code == 401


async def test_user_can_read_own_workspace(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")

    response = await client.get(
        f"/api/v1/workspaces/{alice.workspace_id}", headers=alice.headers
    )

    assert response.status_code == 200
    assert response.json()["id"] == alice.workspace_id
    assert response.json()["role"] == "owner"


async def test_user_cannot_read_another_users_workspace(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")

    response = await client.get(
        f"/api/v1/workspaces/{alice.workspace_id}", headers=bob.headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_other_users_workspace_is_indistinguishable_from_missing(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")

    existing_but_foreign = await client.get(
        f"/api/v1/workspaces/{alice.workspace_id}", headers=bob.headers
    )
    nonexistent = await client.get(
        f"/api/v1/workspaces/{uuid.uuid4()}", headers=bob.headers
    )

    assert existing_but_foreign.status_code == nonexistent.status_code == 404
    assert existing_but_foreign.json() == nonexistent.json()


async def test_list_only_returns_own_workspaces(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")

    alice_list = (await client.get("/api/v1/workspaces", headers=alice.headers)).json()
    bob_list = (await client.get("/api/v1/workspaces", headers=bob.headers)).json()

    assert [w["id"] for w in alice_list] == [alice.workspace_id]
    assert [w["id"] for w in bob_list] == [bob.workspace_id]


async def test_malformed_workspace_id_is_validation_error(make_user, client) -> None:
    alice = await make_user()

    response = await client.get("/api/v1/workspaces/not-a-uuid", headers=alice.headers)

    assert response.status_code == 422
