"""Unit tests for CredentialAccessService (SCRUM-62)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.realtor_repo import RealtorRow
from app.security import CurrentUser
from app.services.credential_service import CredentialAccessService, CredentialUnavailable
from app.services.realtor_review import RealtorNotFound

pytestmark = pytest.mark.asyncio

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")


def _row(*, gov_id_key: str | None) -> RealtorRow:
    return RealtorRow(
        id=uuid4(),
        esvarbon_number="ESV/1234",
        years_of_experience=5,
        coverage_states=["Lagos"],
        coverage_lgas=[],
        completed_deals=0,
        approval_status="pending",
        government_id_s3_key=gov_id_key,
        approved_by=None,
        approved_at=None,
        suspension_reason=None,
        created_at=datetime.now(UTC),
    )


class _StubRealtorRepo:
    def __init__(self, target: RealtorRow | None) -> None:
        self._target = target

    async def get(self, user_id: UUID) -> RealtorRow | None:
        return self._target


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _StubStorage:
    def __init__(self) -> None:
        self.signed: list[tuple[str, int]] = []

    def presigned_get_url(self, key: str, *, expires_seconds: int) -> str:
        self.signed.append((key, expires_seconds))
        return f"https://signed/{key}?e={expires_seconds}"


def _service(
    target: RealtorRow | None,
) -> tuple[CredentialAccessService, _StubAudit, _StubStorage]:
    audit = _StubAudit()
    storage = _StubStorage()
    svc = CredentialAccessService(
        realtors=_StubRealtorRepo(target),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        storage=storage,  # type: ignore[arg-type]
        presign_ttl_seconds=900,
    )
    return svc, audit, storage


async def test_returns_presigned_url_and_audits_access() -> None:
    svc, audit, storage = _service(_row(gov_id_key="realtor-id/abc.pdf"))
    url = await svc.government_id_url(user_id=uuid4(), viewer=_ADMIN)

    assert url == "https://signed/realtor-id/abc.pdf?e=900"
    assert storage.signed == [("realtor-id/abc.pdf", 900)]
    assert len(audit.records) == 1
    assert audit.records[0]["action"] == "realtor.credential_viewed"
    assert audit.records[0]["entity_type"] == "realtor"


async def test_unknown_realtor_is_not_found() -> None:
    svc, audit, _ = _service(None)
    with pytest.raises(RealtorNotFound):
        await svc.government_id_url(user_id=uuid4(), viewer=_ADMIN)
    assert audit.records == []  # no access logged for a miss


async def test_missing_document_raises_unavailable() -> None:
    svc, audit, storage = _service(_row(gov_id_key=None))
    with pytest.raises(CredentialUnavailable):
        await svc.government_id_url(user_id=uuid4(), viewer=_ADMIN)
    assert storage.signed == []  # nothing signed
    assert audit.records == []
