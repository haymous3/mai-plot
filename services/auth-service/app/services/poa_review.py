"""PoA review decision (SCRUM-56) — the legal team approves or rejects.

A pending PoA submission is moved to 'verified' or 'rejected'. A rejection
requires a reason (422 otherwise). Every decision writes an append-only
audit_log row, and the seller is notified of the outcome.

Notification (SCRUM-113): the decision is announced to the seller across in-app +
SMS + email by enqueuing the notification-service `notifications.dispatch` task
(both channels orchestrated there, not via Termii inline). Sending is BEST-EFFORT
— a notification failure is logged but never rolls back a completed legal
decision (the status change is the source of truth).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import UserRepository
from app.security import CurrentUser
from app.services.poa_notifier import PoaNotifier

logger = logging.getLogger(__name__)


class PoaReviewError(RuntimeError):
    pass


class PoaTargetNotFound(PoaReviewError):
    """No live user with that id, or they have no PoA document on file."""


class PoaNotPending(PoaReviewError):
    """The PoA is not awaiting review (already verified/rejected, or never
    submitted)."""


class ReasonRequired(PoaReviewError):
    """A rejection must include a reason."""


@dataclass(frozen=True)
class PoaReviewResult:
    user_id: UUID
    poa_verified_status: str


class PoaReviewService:
    def __init__(
        self,
        *,
        users: UserRepository,
        audit: AuditLogRepository,
        notifier: PoaNotifier,
    ) -> None:
        self._users = users
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
    ) -> PoaReviewResult:
        target = await self._users.get_poa_review_target(user_id)
        if target is None or not target.has_document:
            raise PoaTargetNotFound()
        if target.poa_verified_status != "pending":
            raise PoaNotPending()

        if action == "reject":
            if not reason or not reason.strip():
                raise ReasonRequired()
            new_status, clean_reason = "rejected", reason.strip()
        else:  # approve
            new_status, clean_reason = "verified", None

        await self._users.set_poa_verification(user_id, status=new_status)
        await self._audit.record(
            actor_id=reviewer.user_id,
            actor_role=reviewer.role,
            action=f"poa.{new_status}",
            entity_type="user",
            entity_id=user_id,
            old_value={"poa_verified_status": "pending"},
            new_value={"poa_verified_status": new_status, "reason": clean_reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._notify(user_id=user_id, status=new_status, reason=clean_reason)
        return PoaReviewResult(user_id=user_id, poa_verified_status=new_status)

    async def _notify(self, *, user_id: UUID, status: str, reason: str | None) -> None:
        """Best-effort decision notification (in-app + SMS + email) via
        notification-service. The decision is already committed; a notification
        failure must never undo it, so this is defensively wrapped on top of the
        notifier's own best-effort guarantee."""
        try:
            await self._notifier.poa_decision(user_id=user_id, status=status, reason=reason)
        except Exception as exc:  # noqa: BLE001 — never fail a committed decision
            logger.warning(
                "poa.review.notify_failed",
                extra={"user_id": str(user_id), "status": status, "error": str(exc)},
            )
