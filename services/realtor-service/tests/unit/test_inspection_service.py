"""Unit tests for InspectionService (SCRUM-72)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.repositories.inspection_repo import AssignedRealtorRow, InspectionRow
from app.repositories.transaction_repo import TransactionInfo
from app.security import CurrentUser
from app.services.inspection_service import (
    AssignmentExpired,
    InspectionAlreadyActive,
    InspectionNotFound,
    InspectionNotPending,
    InspectionService,
    NoRealtorAvailable,
    NotAssignedRealtor,
    NotTransactionParty,
    TransactionNotFound,
)

pytestmark = pytest.mark.asyncio

_BUYER = CurrentUser(user_id=uuid4(), role="buyer")
_REALTOR = CurrentUser(user_id=uuid4(), role="realtor")


def _txn() -> TransactionInfo:
    return TransactionInfo(
        id=uuid4(),
        listing_id=uuid4(),
        buyer_id=_BUYER.user_id,
        seller_id=uuid4(),
        stage="inspection_scheduled",
    )


def _inspection(
    *, realtor_id: UUID, status: str = "pending", expires_in_h: float = 2
) -> InspectionRow:
    now = datetime.now(UTC)
    return InspectionRow(
        id=uuid4(),
        transaction_id=uuid4(),
        realtor_id=realtor_id,
        proposed_date=now + timedelta(days=1),
        confirmed_date=None,
        status=status,
        assignment_expires_at=now + timedelta(hours=expires_in_h),
        created_at=now,
        gps_lat=None,
        gps_lng=None,
        report_submitted_at=None,
        report_data=None,
    )


class _StubTxnRepo:
    def __init__(self, txn: TransactionInfo | None) -> None:
        self._txn = txn

    async def get(self, transaction_id: UUID) -> TransactionInfo | None:
        return self._txn


class _StubRealtorRepo:
    def __init__(self, nearest: UUID | None) -> None:
        self._nearest = nearest

    async def find_nearest_approved(
        self, *, listing_id: UUID, radius_m: float, exclude: list[UUID] | None = None
    ) -> UUID | None:
        return self._nearest


class _StubInspectionRepo:
    def __init__(
        self,
        *,
        active: InspectionRow | None = None,
        get_row: InspectionRow | None = None,
        assigned: AssignedRealtorRow | None = None,
    ) -> None:
        self._active = active
        self._get_row = get_row
        self._assigned = assigned
        self.created_realtor: UUID | None = None
        self.accepted: list[UUID] = []

    async def get_active_for_transaction(self, transaction_id: UUID) -> InspectionRow | None:
        return self._active

    async def create(
        self,
        *,
        transaction_id: UUID,
        realtor_id: UUID,
        proposed_date: datetime,
        assignment_window_hours: int,
    ) -> InspectionRow:
        self.created_realtor = realtor_id
        return _inspection(realtor_id=realtor_id)

    async def get(self, inspection_id: UUID) -> InspectionRow | None:
        return self._get_row

    async def mark_accepted(self, inspection_id: UUID) -> bool:
        self.accepted.append(inspection_id)
        return True

    async def latest_assignment_for_transaction(
        self, transaction_id: UUID
    ) -> AssignedRealtorRow | None:
        return self._assigned


class _RecordingNotifier:
    def __init__(self) -> None:
        self.assigned_to: list[UUID] = []

    async def assigned(self, *, realtor_id: UUID, inspection_id: UUID) -> None:
        self.assigned_to.append(realtor_id)


def _service(
    *,
    txn: TransactionInfo | None,
    nearest: UUID | None,
    inspections: _StubInspectionRepo | None = None,
    notifier: _RecordingNotifier | None = None,
) -> tuple[InspectionService, _StubInspectionRepo, _RecordingNotifier]:
    insp = inspections or _StubInspectionRepo()
    n = notifier or _RecordingNotifier()
    svc = InspectionService(
        transactions=_StubTxnRepo(txn),  # type: ignore[arg-type]
        realtors=_StubRealtorRepo(nearest),  # type: ignore[arg-type]
        inspections=insp,  # type: ignore[arg-type]
        notifier=n,
        radius_meters=50_000,
        assignment_window_hours=2,
    )
    return svc, insp, n


# -- request ---------------------------------------------------------------


async def test_request_unknown_transaction() -> None:
    svc, _, _ = _service(txn=None, nearest=uuid4())
    with pytest.raises(TransactionNotFound):
        await svc.request(caller=_BUYER, transaction_id=uuid4(), proposed_date=datetime.now(UTC))


async def test_request_non_party_forbidden() -> None:
    stranger = CurrentUser(user_id=uuid4(), role="buyer")
    svc, _, _ = _service(txn=_txn(), nearest=uuid4())
    with pytest.raises(NotTransactionParty):
        await svc.request(caller=stranger, transaction_id=uuid4(), proposed_date=datetime.now(UTC))


async def test_request_already_active() -> None:
    active = _inspection(realtor_id=uuid4())
    svc, _, _ = _service(
        txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(active=active)
    )
    with pytest.raises(InspectionAlreadyActive):
        await svc.request(caller=_BUYER, transaction_id=uuid4(), proposed_date=datetime.now(UTC))


async def test_request_no_realtor_available() -> None:
    svc, _, _ = _service(txn=_txn(), nearest=None)
    with pytest.raises(NoRealtorAvailable):
        await svc.request(caller=_BUYER, transaction_id=uuid4(), proposed_date=datetime.now(UTC))


async def test_request_assigns_and_notifies() -> None:
    realtor = uuid4()
    svc, insp, notifier = _service(txn=_txn(), nearest=realtor)

    result = await svc.request(
        caller=_BUYER, transaction_id=uuid4(), proposed_date=datetime.now(UTC)
    )

    assert result.realtor_id == realtor
    assert insp.created_realtor == realtor
    assert notifier.assigned_to == [realtor]


# -- accept ----------------------------------------------------------------


async def test_accept_unknown_inspection() -> None:
    svc, _, _ = _service(txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(get_row=None))
    with pytest.raises(InspectionNotFound):
        await svc.accept(caller=_REALTOR, inspection_id=uuid4())


async def test_accept_not_assigned_realtor() -> None:
    row = _inspection(realtor_id=uuid4())  # someone else
    svc, _, _ = _service(txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(get_row=row))
    with pytest.raises(NotAssignedRealtor):
        await svc.accept(caller=_REALTOR, inspection_id=row.id)


async def test_accept_not_pending() -> None:
    row = _inspection(realtor_id=_REALTOR.user_id, status="accepted")
    svc, _, _ = _service(txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(get_row=row))
    with pytest.raises(InspectionNotPending):
        await svc.accept(caller=_REALTOR, inspection_id=row.id)


async def test_accept_expired_window() -> None:
    row = _inspection(realtor_id=_REALTOR.user_id, expires_in_h=-1)  # window elapsed
    svc, _, _ = _service(txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(get_row=row))
    with pytest.raises(AssignmentExpired):
        await svc.accept(caller=_REALTOR, inspection_id=row.id)


async def test_accept_happy() -> None:
    row = _inspection(realtor_id=_REALTOR.user_id)
    repo = _StubInspectionRepo(get_row=row)
    svc, insp, _ = _service(txn=_txn(), nearest=uuid4(), inspections=repo)

    await svc.accept(caller=_REALTOR, inspection_id=row.id)
    assert insp.accepted == [row.id]


# -- assigned_realtor_for_transaction (SCRUM-139) --------------------------


def _assigned(realtor_id: UUID) -> AssignedRealtorRow:
    now = datetime.now(UTC)
    return AssignedRealtorRow(
        inspection_id=uuid4(),
        realtor_id=realtor_id,
        realtor_name="Ada Realtor",
        esvarbon_number="ESV-12345",
        status="accepted",
        proposed_date=now + timedelta(days=1),
        confirmed_date=now + timedelta(days=1),
    )


async def test_assigned_realtor_unknown_transaction() -> None:
    svc, _, _ = _service(txn=None, nearest=uuid4())
    with pytest.raises(TransactionNotFound):
        await svc.assigned_realtor_for_transaction(caller=_BUYER, transaction_id=uuid4())


async def test_assigned_realtor_non_party_forbidden() -> None:
    stranger = CurrentUser(user_id=uuid4(), role="seller")
    svc, _, _ = _service(txn=_txn(), nearest=uuid4())
    with pytest.raises(NotTransactionParty):
        await svc.assigned_realtor_for_transaction(caller=stranger, transaction_id=uuid4())


async def test_assigned_realtor_none_when_no_inspection() -> None:
    svc, _, _ = _service(
        txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(assigned=None)
    )
    result = await svc.assigned_realtor_for_transaction(caller=_BUYER, transaction_id=uuid4())
    assert result is None


async def test_assigned_realtor_returns_identity() -> None:
    realtor = uuid4()
    svc, _, _ = _service(
        txn=_txn(), nearest=uuid4(), inspections=_StubInspectionRepo(assigned=_assigned(realtor))
    )
    result = await svc.assigned_realtor_for_transaction(caller=_BUYER, transaction_id=uuid4())
    assert result is not None
    assert result.realtor_id == realtor
    assert result.realtor_name == "Ada Realtor"
    assert result.esvarbon_number == "ESV-12345"
