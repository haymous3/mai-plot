"""Unit tests for RealtorOnboardingService (SCRUM-71)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.realtor_repo import RealtorRow
from app.services.credentials import InvalidCredential
from app.services.realtor_onboarding import (
    AlreadyRegistered,
    NotRealtorRole,
    RealtorOnboardingService,
)

pytestmark = pytest.mark.asyncio


def _row(*, status: str = "pending") -> RealtorRow:
    return RealtorRow(
        id=uuid4(),
        esvarbon_number="ESV/1234",
        years_of_experience=5,
        coverage_states=["Lagos"],
        coverage_lgas=["Ikeja"],
        completed_deals=0,
        approval_status=status,
        # A realtor onboarded before SCRUM-219 — the column still carries their
        # document key, and nothing in the service reads or overwrites it.
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
        self.create_kwargs: dict[str, object] = {}
        self.base_location: tuple[float, float] | None = None

    async def get(self, user_id: UUID) -> RealtorRow | None:
        return self._existing

    async def create(self, **kwargs: object) -> RealtorRow:
        self.created = True
        self.create_kwargs = kwargs
        return _row()

    async def resubmit(self, **kwargs: object) -> RealtorRow:
        self.resubmitted = True
        return _row()

    async def set_base_location(self, user_id: UUID, *, lat: float, lng: float) -> None:
        self.base_location = (lat, lng)


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _service(repo: _StubRealtorRepo) -> tuple[RealtorOnboardingService, _StubAudit]:
    """No storage argument since SCRUM-219 — onboarding uploads nothing."""
    audit = _StubAudit()
    svc = RealtorOnboardingService(
        realtors=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
    )
    return svc, audit


async def _register(
    svc: RealtorOnboardingService, *, role: str = "realtor", **over: object
) -> object:
    kwargs: dict[str, object] = {
        "user_id": uuid4(),
        "role": role,
        "years_of_experience": 5,
        "coverage_states": ["Lagos"],
        "coverage_lgas": ["Ikeja"],
    }
    kwargs.update(over)
    return await svc.register(**kwargs)  # type: ignore[arg-type]


async def test_non_realtor_role_raises() -> None:
    svc, _ = _service(_StubRealtorRepo())
    with pytest.raises(NotRealtorRole):
        await _register(svc, role="buyer")


async def test_already_registered_when_approved() -> None:
    svc, _ = _service(_StubRealtorRepo(existing=_row(status="approved")))
    with pytest.raises(AlreadyRegistered):
        await _register(svc)


async def test_register_happy_path_creates_and_audits() -> None:
    repo = _StubRealtorRepo()
    svc, audit = _service(repo)

    await _register(svc)

    assert repo.created is True
    assert audit.actions == ["realtor.registered"]
    # SCRUM-207: nothing about a licence number reaches the repo or the audit row.
    assert "esvarbon_number" not in repo.create_kwargs
    # SCRUM-219: and nothing about a document does either. The repo decides the
    # column's value now, not the caller.
    assert "government_id_s3_key" not in repo.create_kwargs


async def test_coverage_required() -> None:
    svc, _ = _service(_StubRealtorRepo())
    with pytest.raises(InvalidCredential):
        await _register(svc, coverage_states=[])


async def test_resubmit_after_rejection() -> None:
    repo = _StubRealtorRepo(existing=_row(status="rejected"))
    svc, _ = _service(repo)

    await _register(svc)

    assert repo.resubmitted is True
    assert repo.created is False


async def test_base_location_set_when_provided() -> None:
    repo = _StubRealtorRepo()
    svc, _ = _service(repo)

    await _register(svc, base_lat=6.5, base_lng=3.4)

    assert repo.base_location == (6.5, 3.4)


async def test_base_location_out_of_range_rejected() -> None:
    svc, _ = _service(_StubRealtorRepo())
    with pytest.raises(InvalidCredential):
        await _register(svc, base_lat=999.0, base_lng=3.4)


async def test_onboarding_refuses_a_base_outside_nigeria() -> None:
    svc, _ = _service(_StubRealtorRepo())
    with pytest.raises(InvalidCredential) as exc:
        await _register(svc, base_lat=51.5, base_lng=-0.12)
    assert exc.value.code == "LOCATION_OUTSIDE_NIGERIA"


# --- set_base_location (SCRUM-214) -------------------------------------------


class _AuditKwargs(_StubAudit):
    def __init__(self) -> None:
        super().__init__()
        self.kwargs: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        await super().record(**kwargs)
        self.kwargs.append(kwargs)


def _with_audit(repo: _StubRealtorRepo) -> tuple[RealtorOnboardingService, _AuditKwargs]:
    audit = _AuditKwargs()
    svc = RealtorOnboardingService(realtors=repo, audit=audit)  # type: ignore[arg-type]
    return svc, audit


async def test_an_onboarded_realtor_sets_a_base_and_it_is_audited_rounded() -> None:
    repo = _StubRealtorRepo(existing=_row())
    svc, audit = _with_audit(repo)

    await svc.set_base_location(user_id=uuid4(), role="realtor", lat=6.431234, lng=3.421987)

    assert repo.base_location == (6.431234, 3.421987)
    [record] = audit.kwargs
    assert record["action"] == "realtor.base_location_set"
    assert record["old_value"] is None
    # ~1 km, not the exact spot someone lives.
    assert record["new_value"] == {"lat": 6.431, "lng": 3.422}


async def test_moving_a_base_records_where_it_was() -> None:
    from dataclasses import replace

    repo = _StubRealtorRepo(existing=replace(_row(), base_lat=9.0768, base_lng=7.3986))
    svc, audit = _with_audit(repo)

    await svc.set_base_location(user_id=uuid4(), role="realtor", lat=6.5244, lng=3.3792)

    assert audit.kwargs[0]["old_value"] == {"lat": 9.077, "lng": 7.399}


async def test_setting_a_base_needs_a_profile_first() -> None:
    from app.services.realtor_onboarding import RealtorNotFound

    svc, _ = _with_audit(_StubRealtorRepo(existing=None))
    with pytest.raises(RealtorNotFound):
        await svc.set_base_location(user_id=uuid4(), role="realtor", lat=6.5, lng=3.4)


async def test_only_realtors_set_a_base() -> None:
    svc, _ = _with_audit(_StubRealtorRepo(existing=_row()))
    with pytest.raises(NotRealtorRole):
        await svc.set_base_location(user_id=uuid4(), role="buyer", lat=6.5, lng=3.4)


async def test_a_base_outside_nigeria_writes_nothing() -> None:
    repo = _StubRealtorRepo(existing=_row())
    svc, audit = _with_audit(repo)
    with pytest.raises(InvalidCredential):
        await svc.set_base_location(user_id=uuid4(), role="realtor", lat=0.0, lng=0.0)
    assert repo.base_location is None
    assert audit.kwargs == []
