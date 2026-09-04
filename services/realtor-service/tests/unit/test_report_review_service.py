"""Unit tests for ReportReviewService (SCRUM-205)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.repositories.inspection_repo import InspectionRow
from app.security import CurrentUser
from app.services.report_review_service import (
    ReportNotFound,
    ReportNotPending,
    ReportReviewService,
    ReviewNoteRequired,
)

pytestmark = pytest.mark.asyncio

_ADMIN = CurrentUser(user_id=uuid4(), role="admin")
_REALTOR_ID = uuid4()


def _inspection(*, review_status: str = "pending", submitted: bool = True) -> InspectionRow:
    now = datetime.now(UTC)
    return InspectionRow(
        id=uuid4(),
        transaction_id=uuid4(),
        realtor_id=_REALTOR_ID,
        proposed_date=now,
        confirmed_date=now,
        status="completed" if submitted else "accepted",
        assignment_expires_at=now,
        created_at=now,
        gps_lat=None,
        gps_lng=None,
        report_submitted_at=now if submitted else None,
        report_data={"photo_keys": ["k1"]} if submitted else None,
        report_review_status=review_status,
        report_reviewed_at=None,
        report_reviewed_by=None,
        report_review_note=None,
        report_revision=1,
    )


class _StubRepo:
    def __init__(self, *, row: InspectionRow | None, applied: bool = True) -> None:
        self._row = row
        self._applied = applied
        self.recorded: dict[str, Any] | None = None

    async def get(self, inspection_id: UUID) -> InspectionRow | None:
        return self._row

    async def record_report_review(
        self, inspection_id: UUID, *, decision: str, reviewer_id: UUID, note: str | None
    ) -> bool:
        self.recorded = {"decision": decision, "reviewer_id": reviewer_id, "note": note}
        return self._applied


class _StubAudit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, **kwargs: Any) -> None:
        self.rows.append(kwargs)


class _StubNotifier:
    def __init__(self, *, boom: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self._boom = boom

    async def decision(self, **kwargs: Any) -> None:
        return None

    async def report_decision(self, **kwargs: Any) -> None:
        if self._boom:
            raise RuntimeError("broker down")
        self.sent.append(kwargs)


def _service(
    *, row: InspectionRow | None, applied: bool = True, boom: bool = False
) -> tuple[ReportReviewService, _StubRepo, _StubAudit, _StubNotifier]:
    repo = _StubRepo(row=row, applied=applied)
    audit = _StubAudit()
    notifier = _StubNotifier(boom=boom)
    svc = ReportReviewService(inspections=repo, audit=audit, notifier=notifier)  # type: ignore[arg-type]
    return svc, repo, audit, notifier


async def test_approve_records_decision_audit_and_notification() -> None:
    insp = _inspection()
    svc, repo, audit, notifier = _service(row=insp)

    result = await svc.review(inspection_id=insp.id, reviewer=_ADMIN, action="approve", note=None)

    assert result.report_review_status == "approved"
    assert repo.recorded == {"decision": "approved", "reviewer_id": _ADMIN.user_id, "note": None}
    assert audit.rows[0]["action"] == "inspection.report_approved"
    # The realtor is the one notified, not the reviewer.
    assert notifier.sent[0]["user_id"] == _REALTOR_ID
    assert notifier.sent[0]["status"] == "approved"


async def test_reject_requires_a_note() -> None:
    insp = _inspection()
    svc, repo, _, _ = _service(row=insp)

    with pytest.raises(ReviewNoteRequired):
        await svc.review(inspection_id=insp.id, reviewer=_ADMIN, action="reject", note="   ")

    # Nothing was written — the realtor is not left with a rejection and no reason.
    assert repo.recorded is None


async def test_reject_carries_the_note_to_the_realtor() -> None:
    insp = _inspection()
    svc, repo, audit, notifier = _service(row=insp)

    await svc.review(
        inspection_id=insp.id, reviewer=_ADMIN, action="reject", note="  Photos too dark.  "
    )

    assert repo.recorded is not None
    assert repo.recorded["note"] == "Photos too dark."
    assert audit.rows[0]["action"] == "inspection.report_rejected"
    assert notifier.sent[0]["note"] == "Photos too dark."


async def test_approve_may_carry_an_optional_note() -> None:
    insp = _inspection()
    svc, repo, _, _ = _service(row=insp)

    await svc.review(inspection_id=insp.id, reviewer=_ADMIN, action="approve", note="Thorough.")

    assert repo.recorded is not None
    assert repo.recorded["note"] == "Thorough."


async def test_audit_records_the_real_previous_status() -> None:
    insp = _inspection()
    svc, _, audit, _ = _service(row=insp)

    await svc.review(inspection_id=insp.id, reviewer=_ADMIN, action="approve", note=None)

    row = audit.rows[0]
    assert row["old_value"] == {"report_review_status": "pending"}
    assert row["new_value"]["report_review_status"] == "approved"
    assert row["new_value"]["revision"] == 1


async def test_missing_inspection_is_not_found() -> None:
    svc, _, _, _ = _service(row=None)
    with pytest.raises(ReportNotFound):
        await svc.review(inspection_id=uuid4(), reviewer=_ADMIN, action="approve", note=None)


async def test_inspection_without_a_submitted_report_is_not_found() -> None:
    svc, _, _, _ = _service(row=_inspection(submitted=False, review_status="not_submitted"))
    with pytest.raises(ReportNotFound):
        await svc.review(inspection_id=uuid4(), reviewer=_ADMIN, action="approve", note=None)


async def test_already_decided_report_is_rejected() -> None:
    svc, _, _, _ = _service(row=_inspection(review_status="approved"))
    with pytest.raises(ReportNotPending):
        await svc.review(inspection_id=uuid4(), reviewer=_ADMIN, action="reject", note="no")


async def test_losing_the_race_to_another_admin_is_a_conflict() -> None:
    # The row read as 'pending' but the guarded UPDATE matched nothing, i.e. a
    # second admin decided in between. Exactly one decision must win.
    insp = _inspection()
    svc, _, audit, notifier = _service(row=insp, applied=False)

    with pytest.raises(ReportNotPending):
        await svc.review(inspection_id=insp.id, reviewer=_ADMIN, action="approve", note=None)

    # The loser writes no audit row and sends no notification.
    assert audit.rows == []
    assert notifier.sent == []


async def test_a_broken_notifier_never_undoes_a_committed_decision() -> None:
    insp = _inspection()
    svc, repo, audit, _ = _service(row=insp, boom=True)

    result = await svc.review(inspection_id=insp.id, reviewer=_ADMIN, action="approve", note=None)

    assert result.report_review_status == "approved"
    assert repo.recorded is not None
    assert audit.rows[0]["action"] == "inspection.report_approved"
