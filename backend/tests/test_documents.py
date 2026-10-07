import json
import uuid
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.storage.local import get_file_storage
from app.tools import default_registry
from app.tools.base import ToolContext
from tests.test_extract import make_docx, make_pdf


def docs_url(workspace_id: str) -> str:
    return f"/api/v1/workspaces/{workspace_id}/documents"


async def upload(
    client: AsyncClient, user, name: str = "notes.txt", data: bytes = b"hello world", expect=202
) -> dict:
    response = await client.post(
        docs_url(user.workspace_id),
        files={"file": (name, data, "application/octet-stream")},
        headers=user.headers,
    )
    assert response.status_code == expect, response.text
    return response.json()


async def get_doc(client: AsyncClient, user, doc_id: str) -> dict:
    response = await client.get(f"{docs_url(user.workspace_id)}/{doc_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def search(client: AsyncClient, user, q: str, **params) -> list[dict]:
    response = await client.get(
        f"{docs_url(user.workspace_id)}/search", params={"q": q, **params}, headers=user.headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def set_status(doc_id: str, status: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            text("UPDATE documents SET status = :status WHERE id = :id"),
            {"status": status, "id": doc_id},
        )
        await session.commit()


BUDGET = b"The quarterly budget review covers marketing spend, headcount and travel costs."
HIKING = b"Weekend hiking trip: pack water, trail mix, a map and warm layers for the summit."


# --- Upload and processing ---------------------------------------------------


async def test_upload_is_accepted_then_processed_in_the_background(make_user, client) -> None:
    alice = await make_user()

    created = await upload(client, alice, "budget.txt", BUDGET)
    document = await get_doc(client, alice, created["id"])

    assert created["status"] == "pending"  # the response does not wait for processing
    assert created["filename"] == "budget.txt"
    assert created["content_type"] == "text/plain"
    assert created["size_bytes"] == len(BUDGET)
    assert document["status"] == "ready"
    assert document["chunk_count"] == 1
    assert document["error"] is None
    assert document["processed_at"] is not None


async def test_pdf_and_docx_are_processed(make_user, client) -> None:
    alice = await make_user()

    pdf = await upload(client, alice, "report.pdf", make_pdf("Annual revenue report"))
    docx = await upload(client, alice, "plan.docx", make_docx("Migration plan", "Phase one"))

    assert (await get_doc(client, alice, pdf["id"]))["status"] == "ready"
    assert (await get_doc(client, alice, docx["id"]))["status"] == "ready"
    assert (await search(client, alice, "annual revenue"))[0]["filename"] == "report.pdf"


async def test_long_documents_are_split_into_chunks(make_user, client) -> None:
    alice = await make_user()
    body = "\n\n".join(f"Section {i}. " + "Lorem ipsum dolor sit amet. " * 20 for i in range(20))

    created = await upload(client, alice, "long.md", body.encode())

    assert (await get_doc(client, alice, created["id"]))["chunk_count"] > 5


async def test_corrupt_file_is_marked_failed_with_a_reason(make_user, client) -> None:
    alice = await make_user()

    created = await upload(client, alice, "broken.pdf", b"%PDF-1.4 this is not a pdf")
    document = await get_doc(client, alice, created["id"])

    assert document["status"] == "failed"
    assert "corrupt" in document["error"]
    assert document["chunk_count"] == 0


async def test_upload_validation(make_user, client, monkeypatch) -> None:
    alice = await make_user()
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 2048)

    unsupported = await upload(client, alice, "malware.exe", b"MZ...", expect=422)
    empty = await upload(client, alice, "empty.txt", b"", expect=422)
    spoofed = await upload(client, alice, "fake.pdf", b"just text", expect=422)
    too_big = await upload(client, alice, "big.txt", b"x" * 2049, expect=413)
    no_file = await client.post(docs_url(alice.workspace_id), headers=alice.headers)

    assert unsupported["error"]["code"] == "INVALID_UPLOAD"
    assert empty["error"]["code"] == "INVALID_UPLOAD"
    assert spoofed["error"]["code"] == "INVALID_UPLOAD"
    assert too_big["error"]["code"] == "UPLOAD_TOO_LARGE"
    assert no_file.status_code == 422
    listing = (await client.get(docs_url(alice.workspace_id), headers=alice.headers)).json()
    assert listing["total"] == 0


async def test_filenames_are_sanitized_and_never_used_as_paths(make_user, client) -> None:
    alice = await make_user()

    traversal = await upload(client, alice, "../../etc/passwd.txt", b"data")
    windows = await upload(client, alice, "C:\\Users\\x\\secret.txt", b"data")

    assert traversal["filename"] == "passwd.txt"
    assert windows["filename"] == "secret.txt"
    storage_root = get_file_storage().root
    stored = [p for p in storage_root.rglob("*") if p.is_file()]
    assert stored and all(p.is_relative_to(storage_root) for p in stored)
    assert not any("passwd" in p.name or "secret" in p.name for p in stored)


async def test_requires_authentication(make_user, client) -> None:
    alice = await make_user()

    response = await client.get(docs_url(alice.workspace_id))

    assert response.status_code == 401


# --- Listing, download, reprocess, delete --------------------------------------


async def test_list_filters_by_status_and_paginates(make_user, client) -> None:
    alice = await make_user()
    await upload(client, alice, "a.txt", b"alpha")
    await upload(client, alice, "b.txt", b"bravo")
    await upload(client, alice, "bad.pdf", b"%PDF-1.4 nope")
    url = docs_url(alice.workspace_id)

    everything = (await client.get(url, headers=alice.headers)).json()
    failed = (await client.get(url, params={"status": "failed"}, headers=alice.headers)).json()
    page = (await client.get(url, params={"limit": 2}, headers=alice.headers)).json()

    assert everything["total"] == 3
    assert [d["filename"] for d in failed["items"]] == ["bad.pdf"]
    assert len(page["items"]) == 2 and page["total"] == 3
    assert everything["items"][0]["filename"] == "bad.pdf"  # newest first


async def test_download_returns_the_original_as_an_attachment(make_user, client) -> None:
    alice = await make_user()
    created = await upload(client, alice, "budget.txt", BUDGET)

    response = await client.get(
        f"{docs_url(alice.workspace_id)}/{created['id']}/download", headers=alice.headers
    )

    assert response.status_code == 200
    assert response.content == BUDGET
    assert "attachment" in response.headers["content-disposition"]
    assert "budget.txt" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_reprocess_rebuilds_chunks_without_duplicates(make_user, client) -> None:
    alice = await make_user()
    created = await upload(client, alice, "budget.txt", BUDGET)
    url = f"{docs_url(alice.workspace_id)}/{created['id']}/reprocess"

    response = await client.post(url, headers=alice.headers)
    document = await get_doc(client, alice, created["id"])

    assert response.status_code == 202
    assert document["status"] == "ready" and document["chunk_count"] == 1
    assert len(await search(client, alice, "quarterly budget")) == 1


async def test_reprocess_is_refused_while_processing(make_user, client) -> None:
    alice = await make_user()
    created = await upload(client, alice, "budget.txt", BUDGET)
    await set_status(created["id"], "processing")

    response = await client.post(
        f"{docs_url(alice.workspace_id)}/{created['id']}/reprocess", headers=alice.headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DOCUMENT_BUSY"


async def test_delete_removes_row_chunks_and_file(make_user, client) -> None:
    alice = await make_user()
    created = await upload(client, alice, "budget.txt", BUDGET)
    url = f"{docs_url(alice.workspace_id)}/{created['id']}"
    async with SessionLocal() as session:
        key = await session.scalar(
            text("SELECT storage_key FROM documents WHERE id = :id"), {"id": created["id"]}
        )
    assert get_file_storage().path_of(key).exists()

    response = await client.delete(url, headers=alice.headers)

    assert response.status_code == 204
    assert (await client.get(url, headers=alice.headers)).status_code == 404
    assert not get_file_storage().path_of(key).exists()
    assert await search(client, alice, "quarterly budget") == []
    async with SessionLocal() as session:
        left = await session.scalar(text("SELECT count(*) FROM document_chunks"))
    assert left == 0


async def test_unknown_document_is_404(make_user, client) -> None:
    alice = await make_user()

    response = await client.get(
        f"{docs_url(alice.workspace_id)}/{uuid.uuid4()}", headers=alice.headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


# --- Search -------------------------------------------------------------------


async def test_search_ranks_the_most_relevant_document_first(make_user, client) -> None:
    alice = await make_user()
    await upload(client, alice, "budget.txt", BUDGET)
    await upload(client, alice, "hiking.txt", HIKING)

    budget_hits = await search(client, alice, "budget review for marketing")
    hiking_hits = await search(client, alice, "what to pack for the hiking summit")

    assert budget_hits[0]["filename"] == "budget.txt"
    assert hiking_hits[0]["filename"] == "hiking.txt"
    assert budget_hits[0]["score"] > budget_hits[1]["score"]
    assert {"document_id", "chunk_index", "content", "score"} <= budget_hits[0].keys()


async def test_search_respects_limit_and_ignores_unfinished_documents(make_user, client) -> None:
    alice = await make_user()
    good = await upload(client, alice, "budget.txt", BUDGET)
    await upload(client, alice, "hiking.txt", HIKING)

    await set_status(good["id"], "pending")
    assert [h["filename"] for h in await search(client, alice, "budget")] == ["hiking.txt"]

    await set_status(good["id"], "ready")
    assert len(await search(client, alice, "budget")) == 2
    assert len(await search(client, alice, "budget", limit=1)) == 1


async def test_search_validation(make_user, client) -> None:
    alice = await make_user()
    url = f"{docs_url(alice.workspace_id)}/search"

    assert (await client.get(url, headers=alice.headers)).status_code == 422
    assert (await client.get(url, params={"q": ""}, headers=alice.headers)).status_code == 422
    assert (
        await client.get(url, params={"q": "x", "limit": 99}, headers=alice.headers)
    ).status_code == 422


# --- Workspace isolation -----------------------------------------------------


async def test_other_workspaces_cannot_see_or_search_documents(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    created = await upload(client, alice, "budget.txt", BUDGET)
    alice_doc = f"{docs_url(alice.workspace_id)}/{created['id']}"
    bobs_url_for_it = f"{docs_url(bob.workspace_id)}/{created['id']}"

    # Bob is not a member of Alice's workspace
    assert (await client.get(alice_doc, headers=bob.headers)).status_code == 404
    assert (await client.get(docs_url(alice.workspace_id), headers=bob.headers)).status_code == 404
    # Alice's document id does not resolve inside Bob's own workspace either
    assert (await client.get(bobs_url_for_it, headers=bob.headers)).status_code == 404
    assert (await client.delete(bobs_url_for_it, headers=bob.headers)).status_code == 404
    assert await search(client, bob, "quarterly budget review") == []
    assert (await get_doc(client, alice, created["id"]))["status"] == "ready"


# --- Assistant tool ---------------------------------------------------------------


async def test_assistant_tool_searches_only_the_current_workspace(make_user, client) -> None:
    alice = await make_user("alice@example.com", "Alice")
    bob = await make_user("bob@example.com", "Bob")
    await upload(client, alice, "budget.txt", BUDGET)

    async def run(user) -> dict:
        async with SessionLocal() as session:
            ctx = ToolContext(
                session=session,
                workspace_id=uuid.UUID(user.workspace_id),
                user_id=uuid.UUID(user.user_id),
                timezone=ZoneInfo("UTC"),
            )
            outcome = await default_registry().execute(
                "search_documents", {"query": "quarterly budget"}, ctx
            )
            return json.loads(outcome.content)

    alice_result, bob_result = await run(alice), await run(bob)

    assert alice_result["ok"] and alice_result["passages"][0]["filename"] == "budget.txt"
    assert bob_result == {"ok": True, "passages": []}
