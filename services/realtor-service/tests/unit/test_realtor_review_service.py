"""Unit tests for RealtorReviewService (SCRUM-71)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.realtor_repo import RealtorRow
from app.security import CurrentUser
from app.services.realtor_review import (
    RealtorNotActionable,
    RealtorNotFound,
    RealtorReviewService,
    ReasonRequired,
)

pytestmark = pytest.mark.asyncio

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")


def _row(*, status: str) -> RealtorRow:
    return RealtorRow(
        id=uuid4(),
        esvarbon_number="ESV/1234",
        years_of_experience=5,
        coverage_states=["Lagos"],
        coverage_lgas=[],
        completed_deals=0,
        approval_status=status,
        government_id_s3_key="realtor-id/x.pdf",
        approved_by=None,
        approved_at=None,
        suspension_reason=None,
        created_at=datetime.now(UTC),
    )


class _StubRealtorRepo:
    def __init__(self, target: RealtorRow | None) -> None:
        self._target = target
        self.decision: dict[str, object] | None = None

    async def get(self, user_id: UUID) -> RealtorRow | None:
        return self._target

    async def set_decision(
        self, *, user_id: UUID, status: str, approved_by: UUID, suspension_reason: str | None
    ) -> bool:
        self.decision = {"status": status, "reason": suspension_reason}
        return True


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


class _RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        self.calls.append({"status": status, "reason": reason})


class _RaisingNotifier:
    async def decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        raise RuntimeError("broker down")


def _service(
    target: RealtorRow | None, notifier: object | None = None
) -> tuple[RealtorReviewService, _StubRealtorRepo, _StubAudit, _RecordingNotifier]:
    repo = _StubRealtorRepo(target)
    audit = _StubAudit()
    n = notifier or _RecordingNotifier()
    svc = RealtorReviewService(
        realtors=repo,  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
        notifier=n,  # type: ignore[arg-type]
    )
    return svc, repo, audit, n  # type: ignore[return-value]


async def test_approve_from_pending() -> None:
    svc, repo, audit, notifier = _service(_row(status="pending"))
    result = await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="approve", reason=None)

    assert result.approval_status == "approved"
    assert repo.decision == {"status": "approved", "reason": None}
    assert audit.actions == ["realtor.approved"]
    assert notifier.calls == [{"status": "approved", "reason": None}]


async def test_reject_requires_reason() -> None:
    svc, repo, _, _ = _service(_row(status="pending"))
    with pytest.raises(ReasonRequired):
        await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="reject", reason="  ")
    assert repo.decision is None


async def test_reject_with_reason() -> None:
    svc, repo, audit, notifier = _service(_row(status="pending"))
    result = await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="reject", reason="blurry ID")
    assert result.approval_status == "rejected"
    assert repo.decision == {"status": "rejected", "reason": "blurry ID"}
    assert notifier.calls == [{"status": "rejected", "reason": "blurry ID"}]


async def test_approve_non_pending_is_not_actionable() -> None:
    svc, _, _, _ = _service(_row(status="approved"))
    with pytest.raises(RealtorNotActionable):
        await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="approve", reason=None)


async def test_suspend_requires_approved() -> None:
    svc, _, _, _ = _service(_row(status="pending"))
    with pytest.raises(RealtorNotActionable):
        await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="suspend", reason="fraud")


async def test_suspend_from_approved() -> None:
    svc, repo, _, _ = _service(_row(status="approved"))
    result = await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="suspend", reason="fraud")
    assert result.approval_status == "suspended"
    assert repo.decision == {"status": "suspended", "reason": "fraud"}


async def test_unknown_realtor_is_not_found() -> None:
    svc, _, _, _ = _service(None)
    with pytest.raises(RealtorNotFound):
        await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="approve", reason=None)


async def test_notifier_failure_does_not_break_decision() -> None:
    svc, repo, audit, _ = _service(_row(status="pending"), notifier=_RaisingNotifier())
    result = await svc.review(user_id=uuid4(), reviewer=_ADMIN, action="approve", reason=None)
    assert result.approval_status == "approved"
    assert repo.decision == {"status": "approved", "reason": None}
    assert audit.actions == ["realtor.approved"]
