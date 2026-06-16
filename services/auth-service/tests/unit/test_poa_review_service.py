"""PoaReviewService — approve/reject, mandatory reason, status guards, SMS."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.adapters.termii import InMemoryTermiiClient
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


def _pending() -> PoaReviewTarget:
    return PoaReviewTarget(poa_verified_status="pending", phone=_PHONE, has_document=True)


def _service(
    repo: _StubUserRepo,
    audit: _StubAudit | None = None,
    termii: InMemoryTermiiClient | None = None,
) -> tuple[PoaReviewService, _StubAudit, InMemoryTermiiClient]:
    a = audit or _StubAudit()
    t = termii or InMemoryTermiiClient()
    svc = PoaReviewService(
        users=repo,  # type: ignore[arg-type]
        audit=a,  # type: ignore[arg-type]
        termii=t,
    )
    return svc, a, t


@pytest.mark.asyncio
async def test_approve_sets_verified_audits_and_notifies() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, termii = _service(repo)
    uid = uuid4()

    result = await svc.review(user_id=uid, reviewer=_REVIEWER, action="approve", reason=None)

    assert result.poa_verified_status == "verified"
    assert repo.set_to == "verified"
    assert audit.records[0]["action"] == "poa.verified"
    assert len(termii.sent) == 1
    assert "verified" in termii.sent[0].message.lower()


@pytest.mark.asyncio
async def test_reject_requires_reason() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, termii = _service(repo)
    with pytest.raises(ReasonRequired):
        await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="reject", reason="  ")
    assert repo.set_to is None
    assert audit.records == []
    assert termii.sent == []


@pytest.mark.asyncio
async def test_reject_with_reason_sets_rejected_and_notifies() -> None:
    repo = _StubUserRepo(_pending())
    svc, audit, termii = _service(repo)

    result = await svc.review(
        user_id=uuid4(), reviewer=_REVIEWER, action="reject", reason="blurry scan"
    )

    assert result.poa_verified_status == "rejected"
    assert repo.set_to == "rejected"
    assert audit.records[0]["action"] == "poa.rejected"
    assert audit.records[0]["new_value"] == {
        "poa_verified_status": "rejected",
        "reason": "blurry scan",
    }
    assert "blurry scan" in termii.sent[0].message


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
async def test_sms_failure_does_not_roll_back_decision() -> None:
    repo = _StubUserRepo(_pending())
    termii = InMemoryTermiiClient(fail_next=True)
    svc, audit, _ = _service(repo, termii=termii)

    # The Termii outage is swallowed — the decision still commits.
    result = await svc.review(user_id=uuid4(), reviewer=_REVIEWER, action="approve", reason=None)
    assert result.poa_verified_status == "verified"
    assert repo.set_to == "verified"
    assert audit.records[0]["action"] == "poa.verified"
