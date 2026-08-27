"""My Documents integration tests — /documents/personal (SCRUM-188).

The properties that matter here are OWNERSHIP (one user must never reach
another's document, and must not be able to tell whether it exists) and the
COUNTS the page renders, which are easy to get subtly wrong once the list is
filtered.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.adapters.document_storage import InMemoryDocumentStorage

_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3" + b"\x00" * 64
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

BASE = "/documents/personal"


def _file(data: bytes, name: str = "passport.pdf", ctype: str = "application/pdf"):  # type: ignore[no-untyped-def]
    return {"file": (name, data, ctype)}


async def _upload(
    http_client: AsyncClient,
    headers: dict[str, str],
    *,
    category: str = "identity",
    data: bytes = _PDF,
    name: str = "passport.pdf",
) -> str:
    resp = await http_client.post(
        BASE, headers=headers, data={"category": category}, files=_file(data, name)
    )
    assert resp.status_code == 201, resp.text
    document_id: str = resp.json()["document_id"]
    return document_id


@pytest.fixture
def owner(
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> tuple[UUID, dict[str, str]]:
    user_id = seed_seller(phone="08050000001", role="buyer")
    return user_id, auth_header(mint_access_token(user_id, "buyer"))


# ── upload ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_stores_the_file_and_records_its_metadata(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    user_id, headers = owner

    await _upload(http_client, headers, name="my passport.pdf")

    listed = await http_client.get(BASE, headers=headers)
    (item,) = listed.json()["items"]
    assert item["file_name"] == "my passport.pdf"
    assert item["size_bytes"] == len(_PDF)
    assert item["content_type"] == "application/pdf"
    # Lands pending — nothing on this path can self-verify a document.
    assert item["verification_status"] == "pending"
    # The object really landed, under a key scoped to its owner.
    (key,) = doc_storage_fake.data
    assert key.startswith(f"users/{user_id}/documents/")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "expected"),
    [(_PDF, "application/pdf"), (_JPEG, "image/jpeg"), (_PNG, "image/png")],
)
async def test_accepts_pdf_jpeg_and_png(
    data: bytes,
    expected: str,
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """The design's own copy says "PDF, JPG, PNG (max 10MB)"."""
    _user_id, headers = owner
    await _upload(http_client, headers, data=data)

    listed = await http_client.get(BASE, headers=headers)
    assert listed.json()["items"][0]["content_type"] == expected


@pytest.mark.asyncio
async def test_a_lying_content_type_is_rejected(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """Client claims application/pdf; the bytes are not. Bytes win, and nothing
    is written to storage or the database."""
    _user_id, headers = owner

    resp = await http_client.post(
        BASE,
        headers=headers,
        data={"category": "identity"},
        files=_file(b"MZ\x90\x00not-a-document", "payload.pdf"),
    )

    assert resp.status_code == 422
    assert resp.json()["error_code"] == "DOCUMENT_FORMAT_INVALID"
    assert doc_storage_fake.data == {}
    listed = await http_client.get(BASE, headers=headers)
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_unknown_category_is_rejected(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    _user_id, headers = owner

    resp = await http_client.post(
        BASE, headers=headers, data={"category": "invented"}, files=_file(_PDF)
    )

    # FastAPI rejects it against the Literal before the service is reached.
    assert resp.status_code == 422
    assert doc_storage_fake.data == {}


@pytest.mark.asyncio
async def test_a_path_traversal_filename_is_reduced_to_a_label(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """The filename is client-controlled and only ever a display label — the
    object is addressed by a server-generated uuid key."""
    _user_id, headers = owner

    await _upload(http_client, headers, name="../../../etc/passwd")

    listed = await http_client.get(BASE, headers=headers)
    assert listed.json()["items"][0]["file_name"] == "passwd"


@pytest.mark.asyncio
async def test_upload_requires_authentication(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
) -> None:
    resp = await http_client.post(BASE, data={"category": "identity"}, files=_file(_PDF))
    assert resp.status_code in (401, 403)


# ── list + counts ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_counts_cover_everything_even_when_the_list_is_filtered(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """The whole point of counting in SQL rather than off the filtered list:
    selecting one tab must not zero every other badge and stat card."""
    _user_id, headers = owner
    await _upload(http_client, headers, category="identity")
    await _upload(http_client, headers, category="identity")
    await _upload(http_client, headers, category="financial")

    filtered = await http_client.get(BASE, headers=headers, params={"category": "financial"})
    body = filtered.json()

    assert len(body["items"]) == 1
    assert body["total"] == 3
    assert body["category_counts"]["identity"] == 2
    assert body["category_counts"]["financial"] == 1


@pytest.mark.asyncio
async def test_empty_categories_and_statuses_are_reported_as_zero(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """The design draws "Property 0" and "Rejected 0". Omitting the key would
    make those rows silently disappear instead."""
    _user_id, headers = owner
    await _upload(http_client, headers, category="identity")

    body = (await http_client.get(BASE, headers=headers)).json()

    assert body["category_counts"] == {"identity": 1, "financial": 0, "property": 0, "other": 0}
    assert body["status_counts"] == {
        "pending": 1,
        "verified": 0,
        "failed": 0,
        "under_review": 0,
    }


@pytest.mark.asyncio
async def test_newest_first(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    _user_id, headers = owner
    await _upload(http_client, headers, name="first.pdf")
    await _upload(http_client, headers, name="second.pdf")

    items = (await http_client.get(BASE, headers=headers)).json()["items"]

    assert [i["file_name"] for i in items] == ["second.pdf", "first.pdf"]


@pytest.mark.asyncio
async def test_one_user_never_sees_anothers_documents(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    _user_id, headers = owner
    await _upload(http_client, headers)

    stranger = seed_seller(phone="08050000002", role="buyer")
    stranger_headers = auth_header(mint_access_token(stranger, "buyer"))

    body = (await http_client.get(BASE, headers=stranger_headers)).json()

    assert body["items"] == []
    assert body["total"] == 0


# ── view ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_view_returns_a_presigned_url(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """The bucket is private (§4), so a pre-signed URL is the only way the file
    reaches a browser."""
    _user_id, headers = owner
    document_id = await _upload(http_client, headers)

    resp = await http_client.get(f"{BASE}/{document_id}/view", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["url"]


@pytest.mark.asyncio
async def test_view_of_someone_elses_document_is_404_not_403(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    """403 would confirm the id is real. Ownership is part of the query, so
    "not yours" and "does not exist" are deliberately indistinguishable."""
    _user_id, headers = owner
    document_id = await _upload(http_client, headers)

    stranger = seed_seller(phone="08050000003", role="buyer")
    stranger_headers = auth_header(mint_access_token(stranger, "buyer"))

    real = await http_client.get(f"{BASE}/{document_id}/view", headers=stranger_headers)
    invented = await http_client.get(f"{BASE}/{uuid4()}/view", headers=stranger_headers)

    assert real.status_code == 404
    assert invented.status_code == 404
    assert real.json() == invented.json()


@pytest.mark.asyncio
async def test_the_personal_path_is_not_captured_by_the_view_route(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """`/documents/{document_id}/view` (SCRUM-98) could swallow
    `/documents/personal/...` by parsing "personal" as an id. Registration
    order prevents it."""
    _user_id, headers = owner

    resp = await http_client.get(BASE, headers=headers)

    assert resp.status_code == 200


# ── delete ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_removes_it_from_the_list_but_keeps_the_object(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """Soft delete. A verified document may already be evidence behind a KYC
    decision (AMLON, §9), so destroying the bytes is a separate deliberate
    step, not a side effect of tidying a list."""
    _user_id, headers = owner
    document_id = await _upload(http_client, headers)
    assert doc_storage_fake.data != {}

    resp = await http_client.delete(f"{BASE}/{document_id}", headers=headers)

    assert resp.status_code == 200
    body = (await http_client.get(BASE, headers=headers)).json()
    assert body["items"] == []
    assert body["total"] == 0
    assert doc_storage_fake.data != {}


@pytest.mark.asyncio
async def test_deleting_twice_is_404(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """Not idempotent by design, so the UI can tell "removed" from "was never
    there"."""
    _user_id, headers = owner
    document_id = await _upload(http_client, headers)
    await http_client.delete(f"{BASE}/{document_id}", headers=headers)

    again = await http_client.delete(f"{BASE}/{document_id}", headers=headers)

    assert again.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_someone_elses_document(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    _user_id, headers = owner
    document_id = await _upload(http_client, headers)

    stranger = seed_seller(phone="08050000004", role="buyer")
    stranger_headers = auth_header(mint_access_token(stranger, "buyer"))
    resp = await http_client.delete(f"{BASE}/{document_id}", headers=stranger_headers)

    assert resp.status_code == 404
    # Still there for its actual owner.
    assert len((await http_client.get(BASE, headers=headers)).json()["items"]) == 1


@pytest.mark.asyncio
async def test_a_soft_deleted_document_cannot_be_viewed(
    clean_tables: None,
    http_client: AsyncClient,
    doc_storage_fake: InMemoryDocumentStorage,
    owner: tuple[UUID, dict[str, str]],
) -> None:
    """The object survives the delete, so the view route must stop serving it
    on the row's state rather than on the object's absence."""
    _user_id, headers = owner
    document_id = await _upload(http_client, headers)
    await http_client.delete(f"{BASE}/{document_id}", headers=headers)

    resp = await http_client.get(f"{BASE}/{document_id}/view", headers=headers)

    assert resp.status_code == 404
