"""Realtor credential review (SCRUM-71) — admin approves / rejects / suspends.

A pending application is moved to 'approved' or 'rejected'; an approved realtor
can be 'suspended'. Reject + suspend require a reason. Every decision writes an
append-only audit_log row and notifies the realtor (best-effort, never rolls
back the committed decision).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.realtor_repo import RealtorRepository
from app.security import CurrentUser
from app.services.realtor_notifier import RealtorNotifier

logger = logging.getLogger(__name__)

# action -> (new status, the status it must currently be in)
_TRANSITIONS = {
    "approve": ("approved", "pending"),
    "reject": ("rejected", "pending"),
    "suspend": ("suspended", "approved"),
}
_REASON_REQUIRED = {"reject", "suspend"}


class RealtorReviewError(RuntimeError):
    pass


class RealtorNotFound(RealtorReviewError):
    """No realtor profile with that id."""


class RealtorNotActionable(RealtorReviewError):
    """The realtor is not in a state this action allows (e.g. approving a
    non-pending application, or suspending one that isn't approved)."""


class ReasonRequired(RealtorReviewError):
    """Reject/suspend must include a reason."""


@dataclass(frozen=True)
class RealtorReviewResult:
    user_id: UUID
    approval_status: str


class RealtorReviewService:
    def __init__(
        self,
        *,
        realtors: RealtorRepository,
        audit: AuditLogRepository,
        notifier: RealtorNotifier,
    ) -> None:
        self._realtors = realtors
        self._audit = audit
        self._notifier = notifier

    async def review(
        self,
        *,
        user_id: UUID,
        reviewer: CurrentUser,
        action: str,
        reason: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RealtorReviewResult:
        new_status, required_from = _TRANSITIONS[action]

        target = await self._realtors.get(user_id)
        if target is None:
            raise RealtorNotFound()
        if target.approval_status != required_from:
            raise RealtorNotActionable()

        clean_reason: str | None = None
        if action in _REASON_REQUIRED:
            if not reason or not reason.strip():
                raise ReasonRequired()
            clean_reason = reason.strip()

        await self._realtors.set_decision(
            user_id=user_id,
            status=new_status,
            approved_by=reviewer.user_id,
            suspension_reason=clean_reason,
        )
        await self._audit.record(
            actor_id=reviewer.user_id,
            actor_role=reviewer.role,
            action=f"realtor.{new_status}",
            entity_type="realtor",
            entity_id=user_id,
            old_value={"approval_status": target.approval_status},
            new_value={"approval_status": new_status, "reason": clean_reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._notify(user_id=user_id, status=new_status, reason=clean_reason)
        return RealtorReviewResult(user_id=user_id, approval_status=new_status)

    async def _notify(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        """Best-effort + defensive: a notification failure must never undo a
        committed decision."""
        try:
            await self._notifier.decision(user_id=user_id, status=status, reason=reason)
        except Exception as exc:  # noqa: BLE001 — never fail a committed decision
            logger.warning(
                "realtor.review.notify_failed",
                extra={"user_id": str(user_id), "status": status, "error": str(exc)},
            )
