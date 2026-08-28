"""AdminDocumentFileService — source dispatch, storage failures, audit trail."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import DocumentObjectMissing, DocumentStorageError
from app.repositories.document_repo import ViewDoc
from app.repositories.user_document_repo import UserDocFile
from app.security import CurrentUser
from app.services.admin_document_file import (
    AdminDocumentFileService,
    DocumentNotFound,
    DocumentUnavailable,
)

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")


class _StubListingRepo:
    def __init__(self, doc: ViewDoc | None) -> None:
        self._doc = doc
        self.calls: list[UUID] = []

    async def get_view(self, document_id: UUID) -> ViewDoc | None:
        self.calls.append(document_id)
        return self._doc


class _StubUserRepo:
    def __init__(self, doc: UserDocFile | None) -> None:
        self._doc = doc
        self.calls: list[UUID] = []

    async def get_for_review(self, document_id: UUID) -> UserDocFile | None:
        self.calls.append(document_id)
        return self._doc


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _StubStorage:
    def __init__(self, payload: bytes | Exception) -> None:
        self._payload = payload
        self.keys: list[str] = []

    async def get(self, key: str) -> bytes:
        self.keys.append(key)
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _listing_doc(key: str = "listings/abc/documents/doc-1.pdf") -> ViewDoc:
    return ViewDoc(
        s3_key=key,
        verification_status="pending",
        listing_id=uuid4(),
        seller_id=uuid4(),
    )


def _personal_doc() -> UserDocFile:
    return UserDocFile(
        s3_key="users/xyz/documents/doc-2.pdf",
        content_type="application/pdf",
        file_name="nin-slip.pdf",
        user_id=uuid4(),
    )


def _service(
    *,
    listing: _StubListingRepo | None = None,
    user: _StubUserRepo | None = None,
    storage: _StubStorage | None = None,
) -> tuple[AdminDocumentFileService, _StubAudit, _StubStorage]:
    audit = _StubAudit()
    store = storage or _StubStorage(b"%PDF-1.4 bytes")
    service = AdminDocumentFileService(
        documents=(listing or _StubListingRepo(None)),  # type: ignore[arg-type]
        user_documents=(user or _StubUserRepo(None)),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        storage=store,  # type: ignore[arg-type]
    )
    return service, audit, store


@pytest.mark.asyncio
async def test_serves_an_unverified_listing_document() -> None:
    """The whole point: a reviewer opens documents that are NOT yet verified.

    `GET /documents/{id}/view` refuses those to every caller, admins included.
    """
    listing = _StubListingRepo(_listing_doc())
    svc, audit, store = _service(listing=listing)

    doc = await svc.get_file(document_id=uuid4(), viewer=_ADMIN)

    assert doc.content == b"%PDF-1.4 bytes"
    assert doc.content_type == "application/pdf"
    assert doc.file_name == "doc-1.pdf"
    assert store.keys == ["listings/abc/documents/doc-1.pdf"]
    assert audit.records[0]["action"] == "document.viewed_for_review"


@pytest.mark.asyncio
async def test_personal_source_uses_the_stored_content_type_and_name() -> None:
    user = _StubUserRepo(_personal_doc())
    listing = _StubListingRepo(_listing_doc())
    svc, _, store = _service(listing=listing, user=user)

    doc = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")

    assert doc.content_type == "application/pdf"
    assert doc.file_name == "nin-slip.pdf"
    assert store.keys == ["users/xyz/documents/doc-2.pdf"]
    # The listing table must not be consulted for a personal document.
    assert listing.calls == []


@pytest.mark.asyncio
async def test_default_source_is_listing() -> None:
    listing = _StubListingRepo(_listing_doc())
    user = _StubUserRepo(_personal_doc())
    svc, _, _ = _service(listing=listing, user=user)

    await svc.get_file(document_id=uuid4(), viewer=_ADMIN)

    assert len(listing.calls) == 1
    assert user.calls == []


@pytest.mark.asyncio
async def test_personal_id_absent_does_not_fall_through_to_listing() -> None:
    listing = _StubListingRepo(_listing_doc())
    user = _StubUserRepo(None)
    svc, _, store = _service(listing=listing, user=user)

    with pytest.raises(DocumentNotFound):
        await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert listing.calls == []
    assert store.keys == []


@pytest.mark.asyncio
async def test_missing_row_is_not_found() -> None:
    svc, audit, _ = _service()
    with pytest.raises(DocumentNotFound):
        await svc.get_file(document_id=uuid4(), viewer=_ADMIN)
    assert audit.records == []


@pytest.mark.asyncio
async def test_missing_object_is_not_found_not_a_server_error() -> None:
    """The row exists, the bucket object does not — still a 404 to the caller."""
    listing = _StubListingRepo(_listing_doc())
    svc, audit, _ = _service(listing=listing, storage=_StubStorage(DocumentObjectMissing("gone")))

    with pytest.raises(DocumentNotFound):
        await svc.get_file(document_id=uuid4(), viewer=_ADMIN)
    assert audit.records == []


@pytest.mark.asyncio
async def test_storage_failure_is_retryable_and_distinct_from_not_found() -> None:
    listing = _StubListingRepo(_listing_doc())
    svc, audit, _ = _service(listing=listing, storage=_StubStorage(DocumentStorageError("s3")))

    with pytest.raises(DocumentUnavailable):
        await svc.get_file(document_id=uuid4(), viewer=_ADMIN)
    assert audit.records == []


@pytest.mark.asyncio
async def test_audit_captures_who_what_and_where_from() -> None:
    listing = _StubListingRepo(_listing_doc())
    svc, audit, _ = _service(listing=listing)
    document_id = uuid4()

    await svc.get_file(
        document_id=document_id,
        viewer=_ADMIN,
        ip_address="10.0.0.4",
        user_agent="Mozilla/5.0",
    )

    record = audit.records[0]
    assert record["actor_id"] == _ADMIN.user_id
    assert record["actor_role"] == "admin"
    assert record["entity_type"] == "document"
    assert record["entity_id"] == document_id
    assert record["new_value"] == {"source": "listing"}
    assert record["ip_address"] == "10.0.0.4"
    assert record["user_agent"] == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_image_content_type_is_inferred_from_the_key() -> None:
    listing = _StubListingRepo(_listing_doc(key="listings/a/documents/scan.JPG"))
    svc, _, _ = _service(listing=listing)

    doc = await svc.get_file(document_id=uuid4(), viewer=_ADMIN)
    assert doc.content_type == "image/jpeg"


@pytest.mark.asyncio
async def test_unknown_extension_falls_back_to_octet_stream() -> None:
    listing = _StubListingRepo(_listing_doc(key="listings/a/documents/mystery.bin"))
    svc, _, _ = _service(listing=listing)

    doc = await svc.get_file(document_id=uuid4(), viewer=_ADMIN)
    assert doc.content_type == "application/octet-stream"


# --------------------------------------------------------------------------
# Serving hardening: these bytes render inline on the ADMIN's own origin
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored_type",
    ["text/html", "image/svg+xml", "application/xhtml+xml", "text/xml"],
)
async def test_active_content_types_are_never_echoed(stored_type: str) -> None:
    """A type the browser executes would be stored XSS with an admin victim.

    detect_document_type() cannot produce these today — it reads magic bytes
    and returns pdf/jpeg/png only — but that invariant lives in another module,
    and this is the boundary where being wrong is dangerous.
    """
    doc = UserDocFile(
        s3_key="users/x/documents/d.pdf",
        content_type=stored_type,
        file_name="payload.pdf",
        user_id=uuid4(),
    )
    svc, _, _ = _service(user=_StubUserRepo(doc))

    served = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert served.content_type == "application/octet-stream"


@pytest.mark.asyncio
@pytest.mark.parametrize("good", ["application/pdf", "image/jpeg", "image/png"])
async def test_the_three_real_document_types_are_served_as_themselves(good: str) -> None:
    doc = UserDocFile(
        s3_key="users/x/documents/d.bin",
        content_type=good,
        file_name="scan.pdf",
        user_id=uuid4(),
    )
    svc, _, _ = _service(user=_StubUserRepo(doc))

    served = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert served.content_type == good


@pytest.mark.asyncio
async def test_a_quote_in_the_filename_cannot_break_out_of_the_header() -> None:
    """file_name is whatever the owner's browser sent, and it gets quoted into
    Content-Disposition. A bare `"` would close the string early."""
    doc = UserDocFile(
        s3_key="users/x/documents/d.pdf",
        content_type="application/pdf",
        file_name='ok".pdf"; download; x="',
        user_id=uuid4(),
    )
    svc, _, _ = _service(user=_StubUserRepo(doc))

    served = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert '"' not in served.file_name


@pytest.mark.asyncio
async def test_crlf_in_the_filename_cannot_inject_a_header() -> None:
    doc = UserDocFile(
        s3_key="users/x/documents/d.pdf",
        content_type="application/pdf",
        file_name="a.pdf\r\nSet-Cookie: admin=1",
        user_id=uuid4(),
    )
    svc, _, _ = _service(user=_StubUserRepo(doc))

    served = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert "\r" not in served.file_name
    assert "\n" not in served.file_name
    assert ":" not in served.file_name


@pytest.mark.asyncio
async def test_a_path_traversal_filename_is_flattened() -> None:
    doc = UserDocFile(
        s3_key="users/x/documents/d.pdf",
        content_type="application/pdf",
        file_name="../../../etc/passwd",
        user_id=uuid4(),
    )
    svc, _, _ = _service(user=_StubUserRepo(doc))

    served = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert "/" not in served.file_name
    assert not served.file_name.startswith(".")


@pytest.mark.asyncio
async def test_a_filename_of_only_punctuation_still_yields_a_name() -> None:
    doc = UserDocFile(
        s3_key="users/x/documents/d.pdf",
        content_type="application/pdf",
        file_name="...",
        user_id=uuid4(),
    )
    svc, _, _ = _service(user=_StubUserRepo(doc))

    served = await svc.get_file(document_id=uuid4(), viewer=_ADMIN, source="personal")
    assert served.file_name == "document"
