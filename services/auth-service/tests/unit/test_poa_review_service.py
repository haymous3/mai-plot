"""PoaReviewService — approve/reject, mandatory reason, status guards, notify."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.repositories.user_repo import PoaReviewTarget
from app.security import CurrentUser
from app.services.poa_review import (
    PoaNotPending,
    PoaReviewService,
    PoaTargetNotFound,
    ReasonRequired,
)

_REVIEWER = CurrentUser(user_id=uuid4(), role="legal_team")
_PHONE = "08012345678"


class _StubUserRepo:
    def __init__(self, target: PoaReviewTarget | None) -> None:
        self._target = target
        self.set_to: str | None = None

    async def get_poa_review_target(self, user_id: UUID) -> PoaReviewTarget | None:
        return self._target

    async def set_poa_verification(self, user_id: UUID, *, status: str) -> None:
        self.set_to = status


class _StubAudit:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def record(self, **kwargs: object) -> None:
        self.records.append(kwargs)


class _RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def poa_decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        self.calls.append({"user_id": user_id, "status": status, "reason": reason})


class _RaisingNotifier:
    async def poa_decision(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        raise RuntimeError("broker down")


def _pending() -> PoaReviewTarget:
    return PoaReviewTarget(poa_verified_status="pending", phone=_PHONE, has_document=True)


def _service(
    repo: _StubUserRepo,
    audit: _StubAudit | None = None,
    notifier: object | None = None,
) -> tuple[PoaReviewService, _StubAudit, _RecordingNotifier]:
    a = audit or _StubAudit()
    n = notifier or _RecordingNotifier()
    svc = PoaReviewService(
        users=repo,  # type: ignore[arg-type]
        audit=a,  # type: ignore[arg-type]
        notifier=n,  # type: ignore[arg-type]
    )
    return svc, a, n  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_approve_sets_verified_audits_and_notifies() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, notifier = _service(repo)
    uid = uuid4()

    result = await svc.review(user_id=uid, reviewer=_REVIEWER, action="approve", reason=None)

    assert result.poa_verified_status == "verified"
    assert repo.set_to == "verified"
    assert audit.records[0]["action"] == "poa.verified"
    assert notifier.calls == [{"user_id": uid, "status": "verified", "reason": None}]


@pytest.mark.asyncio
async def test_reject_requires_reason() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, notifier = _service(repo)
    with pytest.raises(ReasonRequired):
        await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="reject", reason="  ")
    assert repo.set_to is None
    assert audit.records == []
    assert notifier.calls == []


@pytest.mark.asyncio
async def test_reject_with_reason_sets_rejected_and_notifies() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, notifier = _service(repo)
    uid = uuid4()

    result = await svc.review(
        user_id=uid, reviewer=_REVIEWER, action="reject", reason="blurry scan"
    )

    assert result.poa_verified_status == "rejected"
    assert repo.set_to == "rejected"
    assert audit.records[0]["action"] == "poa.rejected"
    assert audit.records[0]["new_value"] == {
        "poa_verified_status": "rejected",
        "reason": "blurry scan",
    }
    assert notifier.calls == [{"user_id": uid, "status": "rejected", "reason": "blurry scan"}]


@pytest.mark.asyncio
async def test_unknown_target_raises() -> None:
    svc, _, _ = _service(_StubUserRepo(None))
    with pytest.raises(PoaTargetNotFound):
        await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="approve", reason=None)


@pytest.mark.asyncio
async def test_missing_document_raises_not_found() -> None:
    target = PoaReviewTarget(poa_verified_status="pending", phone=_PHONE, has_document=False)
    svc, _, _ = _service(_StubUserRepo(target))
    with pytest.raises(PoaTargetNotFound):
        await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="approve", reason=None)


@pytest.mark.asyncio
async def test_non_pending_raises() -> None:
    target = PoaReviewTarget(poa_verified_status="verified", phone=_PHONE, has_document=True)
    svc, _, _ = _service(_StubUserRepo(target))
    with pytest.raises(PoaNotPending):
        await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="approve", reason=None)


@pytest.mark.asyncio
async def test_notify_failure_does_not_roll_back_decision() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, _ = _service(repo, notifier=_RaisingNotifier())

    # A broker outage (notifier raising) is swallowed — the decision still commits.
    result = await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="approve", reason=None)
    assert result.poa_verified_status == "verified"
    assert repo.set_to == "verified"
    assert audit.records[0]["action"] == "poa.verified"
