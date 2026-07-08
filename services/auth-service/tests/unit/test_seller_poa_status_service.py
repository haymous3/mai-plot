"""SellerPoaStatusService — seller gate, status mapping, can_publish, reason (SCRUM-137)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.user_repo import SellerPoaStatus
from app.services.seller_poa_status import (
    NotSeller,
    SellerNotFound,
    SellerPoaStatusService,
)

pytestmark = pytest.mark.asyncio

_SUBMITTED = datetime(2026, 7, 1, 9, 30, tzinfo=UTC)


class _StubUserRepo:
    def __init__(self, status: SellerPoaStatus | None) -> None:
        self._status = status

    async def get_seller_poa_status(self, user_id: UUID) -> SellerPoaStatus | None:
        return self._status


class _StubAudit:
    def __init__(self, reason: str | None = None) -> None:
        self._reason = reason
        self.asked: list[UUID] = []

    async def latest_poa_rejection_reason(self, user_id: UUID) -> str | None:
        self.asked.append(user_id)
        return self._reason


def _service(
    status: SellerPoaStatus | None, *, reason: str | None = None
) -> tuple[SellerPoaStatusService, _StubAudit]:
    audit = _StubAudit(reason)
    svc = SellerPoaStatusService(
        users=_StubUserRepo(status),  # type: ignore[arg-type]
        audit=audit,  # type: ignore[arg-type]
    )
    return svc, audit


def _status(
    authority: str | None, poa_status: str, *, has_document: bool = True
) -> SellerPoaStatus:
    return SellerPoaStatus(
        seller_authority_type=authority,
        poa_verified_status=poa_status,
        has_document=has_document,
        submitted_at=_SUBMITTED if has_document else None,
    )


async def test_non_seller_forbidden() -> None:
    svc, _ = _service(_status("power_of_attorney", "pending"))
    with pytest.raises(NotSeller):
        await svc.get(user_id=uuid4(), role="buyer")


async def test_missing_seller_raises() -> None:
    svc, _ = _service(None)
    with pytest.raises(SellerNotFound):
        await svc.get(user_id=uuid4(), role="seller")


async def test_owner_can_publish_and_no_reason_lookup() -> None:
    svc, audit = _service(_status("owner", "not_applicable", has_document=False), reason="x")
    result = await svc.get(user_id=uuid4(), role="seller")
    assert result.can_publish is True
    assert result.rejection_reason is None
    assert audit.asked == []  # reason only fetched on rejection


async def test_poa_pending_blocks_publish() -> None:
    svc, _ = _service(_status("power_of_attorney", "pending"))
    result = await svc.get(user_id=uuid4(), role="seller")
    assert result.status == "pending"
    assert result.can_publish is False
    assert result.submitted_at == _SUBMITTED.isoformat()


async def test_poa_verified_allows_publish() -> None:
    svc, _ = _service(_status("power_of_attorney", "verified"))
    result = await svc.get(user_id=uuid4(), role="seller")
    assert result.can_publish is True


async def test_poa_rejected_surfaces_reason() -> None:
    svc, audit = _service(_status("power_of_attorney", "rejected"), reason="blurry scan")
    uid = uuid4()
    result = await svc.get(user_id=uid, role="seller")
    assert result.status == "rejected"
    assert result.can_publish is False
    assert result.rejection_reason == "blurry scan"
    assert audit.asked == [uid]
