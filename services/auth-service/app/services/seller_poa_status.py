"""Seller-facing PoA verification tracking (SCRUM-137).

A power-of-attorney seller uploads their PoA during onboarding; the legal team
then moves it pending -> verified | rejected via the admin queue. This service
gives the seller a read of their own PoA status (+ the rejection reason, sourced
from the append-only audit_log) so the dashboard can surface where the review
stands and whether they may yet publish a listing.

Business rule (CLAUDE.md §8.1): a PoA seller cannot publish ANY listing until the
PoA is verified — `can_publish` encodes that so the UI can show the block.
Non-§11: read-only, no financial or state-machine change.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import UserRepository


class NotSeller(RuntimeError):
    """Only seller-role accounts have a PoA status."""


class SellerNotFound(RuntimeError):
    """No live seller account for the caller."""


@dataclass(frozen=True)
class SellerPoaStatusResult:
    authority_type: str | None
    status: str
    has_document: bool
    submitted_at: str | None
    rejection_reason: str | None
    can_publish: bool


class SellerPoaStatusService:
    def __init__(self, *, users: UserRepository, audit: AuditLogRepository) -> None:
        self._users = users
        self._audit = audit

    async def get(self, *, user_id: UUID, role: str) -> SellerPoaStatusResult:
        if role != "seller":
            raise NotSeller
        status = await self._users.get_seller_poa_status(user_id)
        if status is None:
            raise SellerNotFound

        # The reason lives only in the audit trail (no dedicated column); only
        # fetch it when the current decision is a rejection.
        reason = (
            await self._audit.latest_poa_rejection_reason(user_id)
            if status.poa_verified_status == "rejected"
            else None
        )

        # A PoA seller may only publish once verified; an owner is never gated.
        is_poa = status.seller_authority_type == "power_of_attorney"
        can_publish = (not is_poa) or status.poa_verified_status == "verified"

        return SellerPoaStatusResult(
            authority_type=status.seller_authority_type,
            status=status.poa_verified_status,
            has_document=status.has_document,
            submitted_at=status.submitted_at.isoformat() if status.submitted_at else None,
            rejection_reason=reason,
            can_publish=can_publish,
        )
