import uuid

from httpx import AsyncClient


def notes_url(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/notes"


async def create_note(client: AsyncClient, user, **fields) -> dict:
    payload = {"title": "Meeting notes", **fields}
    response = await client.post(
        notes_url(user.workspace_id), json=payload, headers=user.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def search(client: AsyncClient, user, q: str, **params) -> dict:
    response = await client.get(
        notes_url(user.workspace_id), params={"q": q, **params}, headers=user.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def titles(page: dict) -> list[str]:
    return [n["title"] for n in page["items"]]


# --- Create ------------------------------------------------------------------


async def test_create_note_applies_defaults(make_user, client) -> None:
    alice = await make_user()

    note = await create_note(client, alice)

    assert note["title"] == "Meeting notes"
    assert note["content"] == ""
    assert note["tags"] == []
    assert note["workspace_id"] == alice.workspace_id
    assert "search_vector" not in note


async def test_tags_are_normalized_and_deduplicated(make_user, client) -> None:
    alice = await make_user()

    note = await create_note(client, alice, tags=[" Work ", "WORK", "ideas", "Work"])

    assert note["tags"] == ["work", "ideas"]


async def test_create_note_validation(make_user, client) -> None:
    alice = await make_user()
    url = notes_url(alice.workspace_id)

    bad_payloads = [
        {},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 301},
        {"title": "ok", "content": "x" * 100_001},
        {"title": "ok", "tags": ["good", "  "]},
        {"title": "ok", "tags": ["x" * 51]},
        {"title": "ok", "tags": [f"t{i}" for i in range(21)]},
        {"title": "ok", "tags": "not-a-list"},
    ]
    for payload in bad_payloads:
        response = await client.post(url, json=payload, headers=alice.headers)
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_client_cannot_set_workspace(make_user, client) -> None:
    alice = await make_user()

    note = await create_note(client, alice, workspace_id=str(uuid.uuid4()))

    assert note["workspace_id"] == alice.workspace_id


# --- Read / update / delete --------------------------------------------------


async def test_get_note_returns_full_content(make_user, client) -> None:
    alice = await make_user()
    created = await create_note(client, alice, content="x" * 5000)

    response = await client.get(
        f"{notes_url(alice.workspace_id)}/{created['id']}", headers=alice.headers
    )

    assert response.status_code == 200
    assert response.json()["content"] == "x" * 5000


async def test_get_missing_note_returns_standard_404(make_user, client) -> None:
    alice = await make_user()

    response = await client.get(
        f"{notes_url(alice.workspace_id)}/{uuid.uuid4()}", headers=alice.headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOTE_NOT_FOUND"


async def test_partial_update(make_user, client) -> None:
    alice = await make_user()
    created = await create_note(client, alice, content="keep", tags=["a"])
    url = f"{notes_url(alice.workspace_id)}/{created['id']}"

    response = await client.patch(
        url, json={"title": "Renamed", "tags": ["B", "c"]}, headers=alice.headers
    )

    body = response.json()
    assert response.status_code == 200
    assert body["title"] == "Renamed"
    assert body["content"] == "keep"
    assert body["tags"] == ["b", "c"]  # replaced, not merged
    assert body["updated_at"] >= created["updated_at"]


async def test_update_can_clear_content_and_tags(make_user, client) -> None:
    alice = await make_user()
    created = await create_note(client, alice, content="text", tags=["a"])

    response = await client.patch(
        f"{notes_url(alice.workspace_id)}/{created['id']}",
        json={"content": "", "tags": []},
        headers=alice.headers,
    )

    assert response.json()["content"] == ""
    assert response.json()["tags"] == []


async def test_update_rejects_nulls(make_user, client) -> None:
    alice = await make_user()
    created = await create_note(client, alice)
    url = f"{notes_url(alice.workspace_id)}/{created['id']}"

    for field in ("title", "content", "tags"):
        response = await client.patch(url, json={field: None}, headers=alice.headers)
        assert response.status_code == 422, field


async def test_delete_note(make_user, client) -> None:
    alice = await make_user()
    created = await create_note(client, alice)
    url = f"{notes_url(alice.workspace_id)}/{created['id']}"

    deleted = await client.delete(url, headers=alice.headers)
    after = await client.get(url, headers=alice.headers)

    assert deleted.status_code == 204
    assert after.status_code == 404


# --- Listing -----------------------------------------------------------------


async def test_list_returns_preview_not_content(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, content="y" * 1000)

    page = (await client.get(notes_url(alice.workspace_id), headers=alice.headers)).json()

    item = page["items"][0]
    assert "content" not in item
    assert item["preview"] == "y" * 200


async def test_list_orders_by_most_recently_updated(make_user, client) -> None:
    alice = await make_user()
    first = await create_note(client, alice, title="first")
    await create_note(client, alice, title="second")
    # Editing "first" makes it the most recently updated
    await client.patch(
        f"{notes_url(alice.workspace_id)}/{first['id']}",
        json={"content": "edited"},
        headers=alice.headers,
    )

    page = (await client.get(notes_url(alice.workspace_id), headers=alice.headers)).json()

    assert titles(page) == ["first", "second"]


async def test_list_filters_by_tags_requiring_all(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="a", tags=["work", "urgent"])
    await create_note(client, alice, title="b", tags=["work"])
    await create_note(client, alice, title="c", tags=["home"])
    url = notes_url(alice.workspace_id)

    one = (await client.get(url, params={"tag": "work"}, headers=alice.headers)).json()
    both = (
        await client.get(url, params=[("tag", "WORK"), ("tag", "urgent")], headers=alice.headers)
    ).json()
    unknown = (await client.get(url, params={"tag": "nope"}, headers=alice.headers)).json()

    assert sorted(titles(one)) == ["a", "b"]
    assert titles(both) == ["a"]
    assert unknown["total"] == 0


async def test_list_with_malformed_tag_filter_returns_empty(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, tags=["work"])

    response = await client.get(
        notes_url(alice.workspace_id), params={"tag": " "}, headers=alice.headers
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_list_pagination(make_user, client) -> None:
    alice = await make_user()
    for i in range(5):
        await create_note(client, alice, title=f"n{i}")
    url = notes_url(alice.workspace_id)

    page = (
        await client.get(url, params={"limit": 2, "offset": 2}, headers=alice.headers)
    ).json()

    assert page["total"] == 5
    assert len(page["items"]) == 2
    assert (page["limit"], page["offset"]) == (2, 2)


async def test_list_rejects_invalid_pagination(make_user, client) -> None:
    alice = await make_user()
    url = notes_url(alice.workspace_id)

    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": ""}):
        response = await client.get(url, params=params, headers=alice.headers)
        assert response.status_code == 422, params


# --- Search ------------------------------------------------------------------


async def test_search_matches_title_and_content(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="Budget review", content="numbers")
    await create_note(client, alice, title="Groceries", content="remember the budget")
    await create_note(client, alice, title="Unrelated", content="nothing here")

    page = await search(client, alice, "budget")

    assert sorted(titles(page)) == ["Budget review", "Groceries"]
    assert page["total"] == 2


async def test_search_uses_stemming(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="Training log", content="I was running daily")

    assert titles(await search(client, alice, "run")) == ["Training log"]


async def test_search_ranks_title_matches_above_content_matches(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="Shopping", content="proposal mentioned once")
    await create_note(client, alice, title="Proposal draft", content="outline")

    page = await search(client, alice, "proposal")

    assert titles(page) == ["Proposal draft", "Shopping"]


async def test_search_supports_phrases_and_exclusion(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="a", content="rural markets expansion")
    await create_note(client, alice, title="b", content="markets that are rural")
    await create_note(client, alice, title="c", content="rural markets and pricing")

    phrase = await search(client, alice, '"rural markets"')
    excluded = await search(client, alice, "rural -pricing")

    assert sorted(titles(phrase)) == ["a", "c"]
    assert sorted(titles(excluded)) == ["a", "b"]


async def test_search_combines_with_tag_filter(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, title="a", content="budget", tags=["work"])
    await create_note(client, alice, title="b", content="budget", tags=["home"])

    page = await search(client, alice, "budget", tag="work")

    assert titles(page) == ["a"]


async def test_search_reflects_updates(make_user, client) -> None:
    alice = await make_user()
    note = await create_note(client, alice, title="Plain", content="nothing")
    assert (await search(client, alice, "zebra"))["total"] == 0

    await client.patch(
        f"{notes_url(alice.workspace_id)}/{note['id']}",
        json={"content": "a zebra appeared"},
        headers=alice.headers,
    )

    assert titles(await search(client, alice, "zebra")) == ["Plain"]


async def test_search_never_errors_on_odd_input(make_user, client) -> None:
    alice = await make_user()
    await create_note(client, alice, content="text")

    for q in ['"', ")))", "a & | !", "'; DROP TABLE notes; --", "-", "((", "é€😀"]:
        response = await client.get(
            notes_url(alice.workspace_id), params={"q": q}, headers=alice.headers
        )
        assert response.status_code == 200, q


# --- Authentication and workspace isolation ----------------------------------


async def test_notes_require_authentication(make_user, client) -> None:
    alice = await make_user()
    url = notes_url(alice.workspace_id)

    assert (await client.get(url)).status_code == 401
    assert (await client.post(url, json={"title": "x"})).status_code == 401


async def test_user_cannot_access_another_workspaces_notes(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    note = await create_note(client, alice, content="secret plan")
    alice_url = notes_url(alice.workspace_id)

    attempts = [
        await client.get(alice_url, headers=bob.headers),
        await client.get(alice_url, params={"q": "secret"}, headers=bob.headers),
        await client.post(alice_url, json={"title": "injected"}, headers=bob.headers),
        await client.get(f"{alice_url}/{note['id']}", headers=bob.headers),
        await client.patch(
            f"{alice_url}/{note['id']}", json={"title": "hacked"}, headers=bob.headers
        ),
        await client.delete(f"{alice_url}/{note['id']}", headers=bob.headers),
    ]

    for response in attempts:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    intact = await client.get(f"{alice_url}/{note['id']}", headers=alice.headers)
    assert intact.json()["title"] == "Meeting notes"


async def test_note_id_from_another_workspace_is_not_reachable_via_own_workspace(
    make_user, client
) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    note = await create_note(client, alice)
    bob_url = notes_url(bob.workspace_id)

    responses = [
        await client.get(f"{bob_url}/{note['id']}", headers=bob.headers),
        await client.patch(
            f"{bob_url}/{note['id']}", json={"title": "hacked"}, headers=bob.headers
        ),
        await client.delete(f"{bob_url}/{note['id']}", headers=bob.headers),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOTE_NOT_FOUND"


async def test_search_and_tags_never_cross_workspaces(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await create_note(client, alice, title="alice budget", tags=["work"])
    await create_note(client, bob, title="bob budget", tags=["work"])

    alice_hits = await search(client, alice, "budget", tag="work")
    bob_hits = await search(client, bob, "budget", tag="work")

    assert titles(alice_hits) == ["alice budget"]
    assert titles(bob_hits) == ["bob budget"]
