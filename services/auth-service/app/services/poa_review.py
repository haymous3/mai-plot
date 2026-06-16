"""PoA review decision (SCRUM-56) — the legal team approves or rejects.

A pending PoA submission is moved to 'verified' or 'rejected'. A rejection
requires a reason (422 otherwise). Every decision writes an append-only
audit_log row, and the seller is notified of the outcome.

Notification: the decision SMS is sent now via the existing Termii adapter
(CLAUDE.md: SMS is the critical-path channel). Sending is BEST-EFFORT — a
Termii outage is logged but never rolls back a completed legal decision (the
status change is the source of truth). The EMAIL half of the notification is
deferred to notification-service (a follow-up ticket) — there is no SES adapter
in auth-service and notification orchestration belongs in that service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.termii import TermiiClient, TermiiError
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import UserRepository
from app.security import CurrentUser

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
        termii: TermiiClient,
    ) -> None:
        self._users = users
        self._audit = audit
        self._termii = termii

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
        await self._notify(phone=target.phone, status=new_status, reason=clean_reason)
        return PoaReviewResult(user_id=user_id, poa_verified_status=new_status)

    async def _notify(self, *, phone: str, status: str, reason: str | None) -> None:
        """Best-effort decision SMS. Email is deferred to notification-service."""
        if status == "verified":
            message = (
                "Maiplot: your Power-of-Attorney document has been verified. "
                "You can now publish listings."
            )
        else:
            message = (
                "Maiplot: your Power-of-Attorney document was not approved. "
                f"Reason: {reason}. You may re-submit a corrected document."
            )
        try:
            await self._termii.send_sms(phone, message)
        except TermiiError as exc:
            # The decision is already committed; a notification failure must not
            # undo it. Log for follow-up (a retry/reconcile belongs in
            # notification-service when it lands).
            logger.warning(
                "poa.review.sms_failed",
                extra={"phone_suffix": phone[-4:], "status": status, "error": str(exc)},
            )
