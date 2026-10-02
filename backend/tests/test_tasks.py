import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient


def tasks_url(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/tasks"


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


async def create_task(client: AsyncClient, user, **fields) -> dict:
    payload = {"title": "Write proposal", **fields}
    response = await client.post(
        tasks_url(user.workspace_id), json=payload, headers=user.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Create ------------------------------------------------------------------


async def test_create_task_applies_defaults(make_user, client) -> None:
    alice = await make_user()

    task = await create_task(client, alice)

    assert task["title"] == "Write proposal"
    assert task["status"] == "todo"
    assert task["priority"] == "medium"
    assert task["source"] == "manual"
    assert task["workspace_id"] == alice.workspace_id
    assert task["completed_at"] is None
    assert task["due_date"] is None


async def test_create_task_with_all_fields(make_user, client) -> None:
    alice = await make_user()
    due = iso(timedelta(days=2))

    task = await create_task(
        client,
        alice,
        description="Quarterly numbers",
        priority="urgent",
        status="in_progress",
        due_date=due,
    )

    assert task["priority"] == "urgent"
    assert task["status"] == "in_progress"
    assert task["description"] == "Quarterly numbers"
    assert task["due_date"] is not None


async def test_client_cannot_set_source_or_workspace(make_user, client) -> None:
    alice = await make_user()
    other_workspace = str(uuid.uuid4())

    task = await create_task(
        client, alice, source="email", workspace_id=other_workspace
    )

    assert task["source"] == "manual"
    assert task["workspace_id"] == alice.workspace_id


async def test_create_task_validation(make_user, client) -> None:
    alice = await make_user()
    url = tasks_url(alice.workspace_id)

    bad_payloads = [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 301},
        {"title": "ok", "priority": "critical"},
        {"title": "ok", "status": "done"},
        {"title": "ok", "due_date": "2026-10-05T09:00:00"},  # no timezone
        {},
    ]
    for payload in bad_payloads:
        response = await client.post(url, json=payload, headers=alice.headers)
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_completed_task_sets_completed_at(make_user, client) -> None:
    alice = await make_user()

    task = await create_task(client, alice, status="completed")

    assert task["completed_at"] is not None


# --- Read / update / delete --------------------------------------------------


async def test_get_task(make_user, client) -> None:
    alice = await make_user()
    created = await create_task(client, alice)

    response = await client.get(
        f"{tasks_url(alice.workspace_id)}/{created['id']}", headers=alice.headers
    )

    assert response.status_code == 200
    assert response.json() == created


async def test_get_missing_task_returns_standard_404(make_user, client) -> None:
    alice = await make_user()

    response = await client.get(
        f"{tasks_url(alice.workspace_id)}/{uuid.uuid4()}", headers=alice.headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


async def test_partial_update_changes_only_sent_fields(make_user, client) -> None:
    alice = await make_user()
    created = await create_task(client, alice, description="keep me", priority="low")

    response = await client.patch(
        f"{tasks_url(alice.workspace_id)}/{created['id']}",
        json={"title": "New title", "priority": "high"},
        headers=alice.headers,
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "New title"
    assert updated["priority"] == "high"
    assert updated["description"] == "keep me"
    assert updated["updated_at"] >= created["updated_at"]


async def test_update_can_clear_description_and_due_date(make_user, client) -> None:
    alice = await make_user()
    created = await create_task(
        client, alice, description="x", due_date=iso(timedelta(days=1))
    )

    response = await client.patch(
        f"{tasks_url(alice.workspace_id)}/{created['id']}",
        json={"description": None, "due_date": None},
        headers=alice.headers,
    )

    assert response.status_code == 200
    assert response.json()["description"] is None
    assert response.json()["due_date"] is None


async def test_update_rejects_null_for_required_fields(make_user, client) -> None:
    alice = await make_user()
    created = await create_task(client, alice)
    url = f"{tasks_url(alice.workspace_id)}/{created['id']}"

    for field in ("title", "status", "priority"):
        response = await client.patch(url, json={field: None}, headers=alice.headers)
        assert response.status_code == 422, field


async def test_completing_and_reopening_manages_completed_at(make_user, client) -> None:
    alice = await make_user()
    created = await create_task(client, alice)
    url = f"{tasks_url(alice.workspace_id)}/{created['id']}"

    done = (
        await client.patch(url, json={"status": "completed"}, headers=alice.headers)
    ).json()
    reopened = (
        await client.patch(url, json={"status": "todo"}, headers=alice.headers)
    ).json()

    assert done["completed_at"] is not None
    assert reopened["completed_at"] is None


async def test_delete_task(make_user, client) -> None:
    alice = await make_user()
    created = await create_task(client, alice)
    url = f"{tasks_url(alice.workspace_id)}/{created['id']}"

    deleted = await client.delete(url, headers=alice.headers)
    after = await client.get(url, headers=alice.headers)

    assert deleted.status_code == 204
    assert after.status_code == 404


# --- Listing: filters, ordering, pagination ----------------------------------


async def test_list_filters_by_status_and_priority(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="a", status="todo", priority="low")
    await create_task(client, alice, title="b", status="completed", priority="high")
    await create_task(client, alice, title="c", status="todo", priority="high")
    url = tasks_url(alice.workspace_id)

    by_status = (
        await client.get(url, params={"status": "todo"}, headers=alice.headers)
    ).json()
    by_both = (
        await client.get(
            url, params={"status": "todo", "priority": "high"}, headers=alice.headers
        )
    ).json()

    assert by_status["total"] == 2
    assert [t["title"] for t in by_both["items"]] == ["c"]


async def test_list_overdue_filter(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="late", due_date=iso(-timedelta(days=1)))
    await create_task(
        client, alice, title="late but done", status="completed",
        due_date=iso(-timedelta(days=1)),
    )
    await create_task(client, alice, title="future", due_date=iso(timedelta(days=1)))
    await create_task(client, alice, title="undated")
    url = tasks_url(alice.workspace_id)

    overdue = (
        await client.get(url, params={"overdue": "true"}, headers=alice.headers)
    ).json()
    not_overdue = (
        await client.get(url, params={"overdue": "false"}, headers=alice.headers)
    ).json()

    assert [t["title"] for t in overdue["items"]] == ["late"]
    assert {t["title"] for t in not_overdue["items"]} == {
        "late but done", "future", "undated"
    }


async def test_list_due_date_range(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="soon", due_date=iso(timedelta(days=1)))
    await create_task(client, alice, title="later", due_date=iso(timedelta(days=10)))
    url = tasks_url(alice.workspace_id)

    response = await client.get(
        url, params={"due_before": iso(timedelta(days=3))}, headers=alice.headers
    )

    assert [t["title"] for t in response.json()["items"]] == ["soon"]


async def test_list_orders_by_due_date_with_undated_last(make_user, client) -> None:
    alice = await make_user()
    await create_task(client, alice, title="undated")
    await create_task(client, alice, title="later", due_date=iso(timedelta(days=5)))
    await create_task(client, alice, title="sooner", due_date=iso(timedelta(days=1)))

    response = await client.get(tasks_url(alice.workspace_id), headers=alice.headers)

    assert [t["title"] for t in response.json()["items"]] == ["sooner", "later", "undated"]


async def test_list_pagination(make_user, client) -> None:
    alice = await make_user()
    for i in range(5):
        await create_task(
            client, alice, title=f"t{i}", due_date=iso(timedelta(days=i + 1))
        )
    url = tasks_url(alice.workspace_id)

    page1 = (
        await client.get(url, params={"limit": 2, "offset": 0}, headers=alice.headers)
    ).json()
    page3 = (
        await client.get(url, params={"limit": 2, "offset": 4}, headers=alice.headers)
    ).json()

    assert page1["total"] == 5
    assert [t["title"] for t in page1["items"]] == ["t0", "t1"]
    assert (page1["limit"], page1["offset"]) == (2, 0)
    assert [t["title"] for t in page3["items"]] == ["t4"]


async def test_list_rejects_invalid_pagination_and_filters(make_user, client) -> None:
    alice = await make_user()
    url = tasks_url(alice.workspace_id)

    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "nope"}):
        response = await client.get(url, params=params, headers=alice.headers)
        assert response.status_code == 422, params


# --- Authentication and workspace isolation ----------------------------------


async def test_tasks_require_authentication(make_user, client) -> None:
    alice = await make_user()
    url = tasks_url(alice.workspace_id)

    assert (await client.get(url)).status_code == 401
    assert (await client.post(url, json={"title": "x"})).status_code == 401


async def test_user_cannot_access_another_workspaces_tasks(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    task = await create_task(client, alice)
    alice_url = tasks_url(alice.workspace_id)

    attempts = [
        await client.get(alice_url, headers=bob.headers),
        await client.post(alice_url, json={"title": "injected"}, headers=bob.headers),
        await client.get(f"{alice_url}/{task['id']}", headers=bob.headers),
        await client.patch(
            f"{alice_url}/{task['id']}", json={"title": "hacked"}, headers=bob.headers
        ),
        await client.delete(f"{alice_url}/{task['id']}", headers=bob.headers),
    ]

    for response in attempts:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"

    # Nothing changed or leaked
    still_there = await client.get(f"{alice_url}/{task['id']}", headers=alice.headers)
    assert still_there.json()["title"] == "Write proposal"
    assert (await client.get(alice_url, headers=alice.headers)).json()["total"] == 1


async def test_task_id_from_another_workspace_is_not_reachable_via_own_workspace(
    make_user, client
) -> None:
    """Bob uses his *own* workspace in the URL but Alice's task id."""
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    task = await create_task(client, alice)
    bob_url = tasks_url(bob.workspace_id)

    get = await client.get(f"{bob_url}/{task['id']}", headers=bob.headers)
    patch = await client.patch(
        f"{bob_url}/{task['id']}", json={"title": "hacked"}, headers=bob.headers
    )
    delete = await client.delete(f"{bob_url}/{task['id']}", headers=bob.headers)

    for response in (get, patch, delete):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TASK_NOT_FOUND"
    mine = await client.get(f"{tasks_url(alice.workspace_id)}/{task['id']}", headers=alice.headers)
    assert mine.status_code == 200


async def test_each_workspace_lists_only_its_own_tasks(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await create_task(client, alice, title="alice task")
    await create_task(client, bob, title="bob task")

    alice_list = (await client.get(tasks_url(alice.workspace_id), headers=alice.headers)).json()
    bob_list = (await client.get(tasks_url(bob.workspace_id), headers=bob.headers)).json()

    assert [t["title"] for t in alice_list["items"]] == ["alice task"]
    assert [t["title"] for t in bob_list["items"]] == ["bob task"]
