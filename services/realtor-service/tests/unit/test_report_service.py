"""Unit tests for ReportService (SCRUM-73)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adapters.document_storage import InMemoryDocumentStorage
from app.repositories.inspection_repo import InspectionRow
from app.repositories.transaction_repo import TransactionInfo
from app.security import CurrentUser
from app.services.credentials import InvalidCredential
from app.services.inspection_service import InspectionNotFound, NotAssignedRealtor
from app.services.report_service import (
    GpsOutOfRange,
    NotAuthorizedForReport,
    ReportNotFound,
    ReportNotSubmittable,
    ReportService,
    ReportTooEarly,
)

pytestmark = pytest.mark.asyncio

_REALTOR = CurrentUser(user_id=uuid4(), role="realtor")
_BUYER = CurrentUser(user_id=uuid4(), role="buyer")
_SELLER_ID = uuid4()
_JPEG = b"\xff\xd8\xff\xe0 photo"
# ISO-BMFF: a 'ftyp' box at offset 4 → detected as MP4.
_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


def _inspection(
    *,
    realtor_id: UUID = _REALTOR.user_id,
    status: str = "accepted",
    confirmed_offset_h: float = -1,
    submitted: bool = False,
    review_status: str | None = None,
) -> InspectionRow:
    now = datetime.now(UTC)
    return InspectionRow(
        id=uuid4(),
        transaction_id=uuid4(),
        realtor_id=realtor_id,
        proposed_date=now,
        confirmed_date=now + timedelta(hours=confirmed_offset_h),
        status="completed" if submitted else status,
        assignment_expires_at=now,
        created_at=now,
        gps_lat=None,
        gps_lng=None,
        report_submitted_at=now if submitted else None,
        report_data=(
            {"property_condition": "good", "amenities": ["water"], "photo_keys": ["k1", "k2", "k3"]}
            if submitted
            else None
        ),
        report_review_status=review_status or ("pending" if submitted else "not_submitted"),
        report_reviewed_at=None,
        report_reviewed_by=None,
        report_review_note="Photos too dark." if review_status == "rejected" else None,
        report_revision=1,
    )


class _StubInspectionRepo:
    def __init__(self, *, row: InspectionRow | None, within: bool = True) -> None:
        self._row = row
        self._within = within
        self.submitted: dict[str, Any] | None = None
        self.was_resubmission: bool = False

    async def get(self, inspection_id: UUID) -> InspectionRow | None:
        return self._row

    async def submit_report(
        self,
        inspection_id: UUID,
        *,
        gps_lat: float,
        gps_lng: float,
        report_data: dict[str, Any],
        is_resubmission: bool = False,
    ) -> bool:
        self.submitted = report_data
        self.was_resubmission = is_resubmission
        return True

    async def is_point_within_property(
        self, *, listing_id: UUID, lat: float, lng: float, meters: float
    ) -> bool:
        return self._within


class _StubTxnRepo:
    def __init__(self, txn: TransactionInfo | None) -> None:
        self._txn = txn

    async def get(self, transaction_id: UUID) -> TransactionInfo | None:
        return self._txn


class _StubAudit:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def record(self, **kwargs: object) -> None:
        self.actions.append(str(kwargs["action"]))


def _txn(inspection: InspectionRow) -> TransactionInfo:
    return TransactionInfo(
        id=uuid4(),
        listing_id=uuid4(),
        buyer_id=_BUYER.user_id,
        seller_id=_SELLER_ID,
        stage="inspection_scheduled",
    )


def _service(
    *,
    row: InspectionRow | None,
    within: bool = True,
    txn: TransactionInfo | None = None,
    storage: InMemoryDocumentStorage | None = None,
) -> tuple[ReportService, _StubInspectionRepo, InMemoryDocumentStorage]:
    insp = _StubInspectionRepo(row=row, within=within)
    s = storage or InMemoryDocumentStorage()
    svc = ReportService(
        inspections=insp,  # type: ignore[arg-type]
        transactions=_StubTxnRepo(txn),  # type: ignore[arg-type]
        audit=_StubAudit(),  # type: ignore[arg-type]
        storage=s,
        gps_radius_meters=1000,
        min_photos=3,
        photo_max_bytes=1024,
        video_max_bytes=10 * 1024 * 1024,
        presign_ttl_seconds=900,
    )
    return svc, insp, s


async def _submit(
    svc: ReportService, *, inspection_id: UUID, caller: CurrentUser = _REALTOR, **over: object
) -> object:
    kwargs: dict[str, object] = {
        "caller": caller,
        "inspection_id": inspection_id,
        "gps_lat": 6.5,
        "gps_lng": 3.4,
        "property_condition": "good",
        "amenities": ["water"],
        "discrepancies": None,
        "remarks": "ok",
        "photos": [_JPEG, _JPEG, _JPEG],
    }
    kwargs.update(over)
    return await svc.submit(**kwargs)  # type: ignore[arg-type]


# -- submit ----------------------------------------------------------------


async def test_submit_not_found() -> None:
    svc, _, _ = _service(row=None)
    with pytest.raises(InspectionNotFound):
        await _submit(svc, inspection_id=uuid4())


async def test_submit_not_assigned() -> None:
    row = _inspection(realtor_id=uuid4())
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(NotAssignedRealtor):
        await _submit(svc, inspection_id=row.id)


async def test_submit_wrong_status() -> None:
    row = _inspection(status="pending")
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(ReportNotSubmittable):
        await _submit(svc, inspection_id=row.id)


async def test_submit_too_early() -> None:
    row = _inspection(confirmed_offset_h=5)  # confirmed date in the future
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(ReportTooEarly):
        await _submit(svc, inspection_id=row.id)


async def test_submit_invalid_condition() -> None:
    row = _inspection()
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(InvalidCredential):
        await _submit(svc, inspection_id=row.id, property_condition="amazing")


async def test_submit_too_few_photos() -> None:
    row = _inspection()
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(InvalidCredential):
        await _submit(svc, inspection_id=row.id, photos=[_JPEG, _JPEG])


async def test_submit_gps_out_of_range() -> None:
    row = _inspection()
    svc, _, _ = _service(row=row, within=False, txn=_txn(row))
    with pytest.raises(GpsOutOfRange):
        await _submit(svc, inspection_id=row.id)


async def test_submit_happy_stores_and_records() -> None:
    row = _inspection()
    svc, insp, storage = _service(row=row, txn=_txn(row))

    await _submit(svc, inspection_id=row.id)

    assert insp.submitted is not None
    assert len(insp.submitted["photo_keys"]) == 3
    assert insp.submitted["video_key"] is None  # no video by default
    assert len(storage.objects) == 3


async def test_submit_with_video_stores_it() -> None:
    row = _inspection()
    svc, insp, storage = _service(row=row, txn=_txn(row))

    await _submit(svc, inspection_id=row.id, video=_MP4)

    assert insp.submitted is not None
    assert insp.submitted["video_key"] is not None
    assert len(storage.objects) == 4  # 3 photos + 1 video


async def test_submit_invalid_video_type_rejected() -> None:
    row = _inspection()
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(InvalidCredential):
        await _submit(svc, inspection_id=row.id, video=b"not a video file")


# -- view ------------------------------------------------------------------


async def test_view_unauthorized() -> None:
    row = _inspection(submitted=True)
    stranger = CurrentUser(user_id=uuid4(), role="buyer")
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(NotAuthorizedForReport):
        await svc.get_report(caller=stranger, inspection_id=row.id)


async def test_view_no_report_yet() -> None:
    row = _inspection(submitted=False)
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(ReportNotFound):
        await svc.get_report(caller=_BUYER, inspection_id=row.id)


async def test_view_happy_returns_photo_urls() -> None:
    row = _inspection(submitted=True)
    svc, _, _ = _service(row=row, txn=_txn(row))

    view = await svc.get_report(caller=_BUYER, inspection_id=row.id)

    assert view.property_condition == "good"
    assert len(view.photo_urls) == 3


# -- SCRUM-205: resubmitting a rejected report -------------------------------


async def test_rejected_report_can_be_resubmitted_though_status_is_completed() -> None:
    # The inspection stays 'completed' after a rejection (product decision), so
    # the first-submission status guard must not block the redo.
    row = _inspection(submitted=True, review_status="rejected")
    svc, repo, _ = _service(row=row, txn=_txn(row))

    await _submit(svc, inspection_id=row.id)

    assert repo.was_resubmission is True
    assert repo.submitted is not None


async def test_resubmission_skips_the_confirmed_date_guard() -> None:
    # The date guard already passed on the original submission; re-checking it
    # would reject work the realtor was explicitly told to redo.
    row = _inspection(submitted=True, review_status="rejected", confirmed_offset_h=+48)
    svc, repo, _ = _service(row=row, txn=_txn(row))

    await _submit(svc, inspection_id=row.id)

    assert repo.was_resubmission is True


async def test_resubmission_supersedes_the_previous_photos_without_destroying_them() -> None:
    row = _inspection(submitted=True, review_status="rejected")
    svc, repo, _ = _service(row=row, txn=_txn(row))

    await _submit(svc, inspection_id=row.id)

    assert repo.submitted is not None
    superseded = repo.submitted["superseded"]
    assert len(superseded) == 1
    # The old keys are still addressable, tagged with the revision they belonged to.
    assert superseded[0]["revision"] == 1
    assert superseded[0]["photo_keys"] == ["k1", "k2", "k3"]
    assert superseded[0]["review_note"] == "Photos too dark."
    # And the live photo_keys are the NEW ones, not the old.
    assert repo.submitted["photo_keys"] != superseded[0]["photo_keys"]


async def test_an_approved_report_cannot_be_resubmitted() -> None:
    row = _inspection(submitted=True, review_status="approved")
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(ReportNotSubmittable):
        await _submit(svc, inspection_id=row.id)


async def test_a_pending_report_cannot_be_resubmitted() -> None:
    # Still awaiting review — resubmitting would let a realtor swap the report
    # out from under the admin looking at it.
    row = _inspection(submitted=True, review_status="pending")
    svc, _, _ = _service(row=row, txn=_txn(row))
    with pytest.raises(ReportNotSubmittable):
        await _submit(svc, inspection_id=row.id)


async def test_first_submission_is_not_flagged_as_a_resubmission() -> None:
    row = _inspection(status="accepted")
    svc, repo, _ = _service(row=row, txn=_txn(row))

    await _submit(svc, inspection_id=row.id)

    assert repo.was_resubmission is False
    assert repo.submitted is not None
    assert "superseded" not in repo.submitted
