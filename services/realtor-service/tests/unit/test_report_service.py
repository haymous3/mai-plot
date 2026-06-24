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


def _inspection(
    *,
    realtor_id: UUID = _REALTOR.user_id,
    status: str = "accepted",
    confirmed_offset_h: float = -1,
    submitted: bool = False,
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
    )


class _StubInspectionRepo:
    def __init__(self, *, row: InspectionRow | None, within: bool = True) -> None:
        self._row = row
        self._within = within
        self.submitted: dict[str, Any] | None = None

    async def get(self, inspection_id: UUID) -> InspectionRow | None:
        return self._row

    async def submit_report(
        self, inspection_id: UUID, *, gps_lat: float, gps_lng: float, report_data: dict[str, Any]
    ) -> bool:
        self.submitted = report_data
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
    assert len(storage.objects) == 3


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
