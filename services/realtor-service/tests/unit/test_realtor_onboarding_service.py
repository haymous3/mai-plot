"""Unit tests for RealtorOnboardingService (SCRUM-71)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.repositories.realtor_repo import RealtorRow
from app.services.credentials import InvalidCredential
from app.services.realtor_onboarding import (
    AlreadyRegistered,
    NotRealtorRole,
    RealtorOnboardingService,
)

pytestmark = pytest.mark.asyncio

_PDF = b"%PDF-1.4 realtor id"


def _row(*, status: str = "pending") -> RealtorRow:
    return RealtorRow(
        id=uuid4(),
        esvarbon_number="ESV/1234",
        years_of_experience=5,
        coverage_states=["Lagos"],
        coverage_lgas=["Ikeja"],
        completed_deals=0,
        approval_status=status,
        government_id_s3_key="realtor-id/x.pdf",
        approved_by=None,
        approved_at=None,
        suspension_reason=None,
        created_at=datetime.now(UTC),
    )


class _StubRealtorRepo:
    def __init__(self, existing: RealtorRow | None = None) -> None:
        self._existing = existing
        self.created = False
        self.resubmitted = False

    async def get(self, user_id: UUID) -> RealtorRow | None:
        return self._existing

    async def create(self, **kwargs: object) -> RealtorRow:
        self.created = True
        return _row()

    async def resubmit(self, **kwargs: object) -> RealtorRow:
        self.resubmitted = True
        return _row()


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service(
    repo: _StubRealtorRepo, storage: InMemoryDocumentStorage | None = None
) -> tuple[RealtorOnboardingService, InMemoryDocumentStorage, _StubAudit]:
    s = storage or InMemoryDocumentStorage()
    audit = _StubAudit()
    svc = RealtorOnboardingService(
        realtors=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        storage=s,
        max_upload_bytes=1024,
    )
    return svc, s, audit


async def _register(
    svc: RealtorOnboardingService, *, role: str = "realtor", **over: object
) -> object:
    kwargs: dict[str, object] = {
        "user_id": uuid4(),
        "role": role,
        "esvarbon_number": "esv/1234",
        "years_of_experience": 5,
        "coverage_states": ["Lagos"],
        "coverage_lgas": ["Ikeja"],
        "id_document": _PDF,
    }
    kwargs.update(over)
    return await svc.register(**kwargs)  # type: ignore[arg-type]


async def test_non_realtor_role_raises() -> None:
    svc, _, _ = _service(_StubRealtorRepo())
    with pytest.raises(NotRealtorRole):
        await _register(svc, role="buyer")


async def test_already_registered_when_approved() -> None:
    svc, _, _ = _service(_StubRealtorRepo(existing=_row(status="approved")))
    with pytest.raises(AlreadyRegistered):
        await _register(svc)


async def test_register_happy_path_stores_and_audits() -> None:
    repo = _StubRealtorRepo()
    svc, storage, audit = _service(repo)

    await _register(svc)

    assert repo.created is True
    assert len(storage.objects) == 1
    assert audit.actions == ["realtor.registered"]


async def test_invalid_esvarbon_rejected() -> None:
    svc, _, _ = _service(_StubRealtorRepo())
    with pytest.raises(InvalidCredential):
        await _register(svc, esvarbon_number="!!")


async def test_invalid_id_document_rejected() -> None:
    svc, _, _ = _service(_StubRealtorRepo())
    with pytest.raises(InvalidCredential):
        await _register(svc, id_document=b"GIF89a")


async def test_coverage_required() -> None:
    svc, _, _ = _service(_StubRealtorRepo())
    with pytest.raises(InvalidCredential):
        await _register(svc, coverage_states=[])


async def test_resubmit_after_rejection() -> None:
    repo = _StubRealtorRepo(existing=_row(status="rejected"))
    svc, _, _ = _service(repo)

    await _register(svc)

    assert repo.resubmitted is True
    assert repo.created is False
