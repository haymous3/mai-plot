"""Unit tests for LoanDocumentService (SCRUM-131)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.repositories.loan_document_repo import LoanDocRow
from app.security import CurrentUser
from app.services.document import InvalidDocument
from app.services.loan_document_upload import (
    LoanDocumentService,
    LoanDocumentStorageUnavailable,
    LoanNotFound,
    NotLoanOwner,
)

pytestmark = pytest.mark.asyncio

_PDF = b"%PDF-1.4 body"
_PNG = b"\x89PNG\r\n\x1a\n rest"
_BUYER = uuid4()
_LOAN = uuid4()


class _StubLoans:
    def __init__(self, buyer: UUID | None) -> None:
        self._buyer = buyer

    async def get_loan_buyer(self, loan_id: UUID) -> UUID | None:
        return self._buyer


class _StubDocs:
    def __init__(self, rows: list[LoanDocRow] | None = None) -> None:
        self.inserted: list[dict[str, object]] = []
        self._rows = rows or []

    async def insert_document(
        self, *, loan_id: UUID, document_type: str, s3_key: str, uploaded_by: UUID
    ) -> UUID:
        did = uuid4()
        self.inserted.append(
            {
                "loan_id": loan_id,
                "document_type": document_type,
                "s3_key": s3_key,
                "by": uploaded_by,
            }
        )
        return did

    async def list_for_loan(self, loan_id: UUID) -> list[LoanDocRow]:
        return self._rows


def _service(
    loans: _StubLoans, docs: _StubDocs, storage: InMemoryDocumentStorage | None = None
) -> LoanDocumentService:
    return LoanDocumentService(
        loans=loans,  # type: ignore[arg-type]
        documents=docs,  # type: ignore[arg-type]
        storage=storage or InMemoryDocumentStorage(),
        max_bytes=10 * 1024 * 1024,
        presign_ttl_seconds=900,
    )


def _buyer() -> CurrentUser:
    return CurrentUser(user_id=_BUYER, role="buyer")


async def test_upload_stores_and_inserts() -> None:
    docs = _StubDocs()
    storage = InMemoryDocumentStorage()
    result = await _service(_StubLoans(_BUYER), docs, storage).upload(
        loan_id=_LOAN, caller=_buyer(), document_type="bank_statement", data=_PDF
    )
    assert result.verification_status == "pending"
    assert docs.inserted[0]["document_type"] == "bank_statement"
    key = docs.inserted[0]["s3_key"]
    assert isinstance(key, str) and key.startswith(f"loans/{_LOAN}/documents/")
    assert key in storage.objects  # persisted to the private bucket


async def test_png_is_accepted() -> None:
    docs = _StubDocs()
    await _service(_StubLoans(_BUYER), docs).upload(
        loan_id=_LOAN, caller=_buyer(), document_type="passport", data=_PNG
    )
    assert docs.inserted[0]["s3_key"] == docs.inserted[0]["s3_key"]  # inserted (png ok)
    assert str(docs.inserted[0]["s3_key"]).endswith(".png")


async def test_unknown_loan_raises() -> None:
    with pytest.raises(LoanNotFound):
        await _service(_StubLoans(None), _StubDocs()).upload(
            loan_id=_LOAN, caller=_buyer(), document_type="passport", data=_PDF
        )


async def test_non_owner_forbidden() -> None:
    with pytest.raises(NotLoanOwner):
        await _service(_StubLoans(uuid4()), _StubDocs()).upload(
            loan_id=_LOAN, caller=_buyer(), document_type="passport", data=_PDF
        )


async def test_admin_may_upload_for_any_loan() -> None:
    docs = _StubDocs()
    await _service(_StubLoans(uuid4()), docs).upload(
        loan_id=_LOAN,
        caller=CurrentUser(user_id=uuid4(), role="admin"),
        document_type="passport",
        data=_PDF,
    )
    assert len(docs.inserted) == 1


async def test_bad_format_rejected() -> None:
    with pytest.raises(InvalidDocument):
        await _service(_StubLoans(_BUYER), _StubDocs()).upload(
            loan_id=_LOAN, caller=_buyer(), document_type="passport", data=b"not-a-doc"
        )


async def test_storage_failure_surfaces() -> None:
    storage = InMemoryDocumentStorage()
    storage.fail_next = True
    with pytest.raises(LoanDocumentStorageUnavailable):
        await _service(_StubLoans(_BUYER), _StubDocs(), storage).upload(
            loan_id=_LOAN, caller=_buyer(), document_type="bank_statement", data=_PDF
        )


async def test_list_returns_presigned_urls() -> None:
    rows = [
        LoanDocRow(
            id=uuid4(),
            document_type="passport",
            s3_key="loans/x/documents/a.png",
            verification_status="pending",
            created_at=datetime.now(UTC),
        )
    ]
    views = await _service(_StubLoans(_BUYER), _StubDocs(rows)).list_for_loan(
        loan_id=_LOAN, caller=_buyer()
    )
    assert len(views) == 1
    assert views[0].url.startswith("memory://documents/loans/x/documents/a.png")


async def test_list_forbidden_for_stranger() -> None:
    with pytest.raises(NotLoanOwner):
        await _service(_StubLoans(uuid4()), _StubDocs()).list_for_loan(
            loan_id=_LOAN, caller=_buyer()
        )
