"""Realtor credential review (SCRUM-71) — admin approves / rejects / suspends.

A pending application is moved to 'approved' or 'rejected'; an approved realtor
can be 'suspended'. Reject + suspend require a reason. Every decision writes an
append-only audit_log row and notifies the realtor (best-effort, never rolls
back the committed decision).

Approval also ISSUES the realtor's Maihomme registration number (SCRUM-207) —
the identifier they sign in with, since the ESVARBON licence is no longer
collected. Two things about the ordering are deliberate:

  * The number is issued BEFORE the decision is applied. If auth-service cannot
    be reached the whole approval fails with 503 and the realtor stays pending,
    which an admin can retry. The other order would produce an approved realtor
    with no number — and their email login is refused precisely BECAUSE they are
    approved, so that state is a locked account no admin action can unpick.
  * Issuance is idempotent on the auth side, so a retried approval (or one whose
    own commit failed after the number was minted) reuses the same number rather
    than minting a second one that would also authenticate.

Reject and suspend issue nothing: a realtor who was never approved has no
number, which is exactly what keeps their email login working so they can see
the decision and re-submit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.registration_number import RegistrationNumberIssuer
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
    # Set on approval only. Returned so the admin UI can show the number it just
    # issued — if the email bounces, the reviewer is the only one who can hand it
    # over, and they cannot read it back out of auth-service.
    registration_number: str | None = None


class RealtorReviewService:
    def __init__(
        self,
        *,
        realtors: RealtorRepository,
        audit: AuditLogRepository,
        notifier: RealtorNotifier,
        registration_numbers: RegistrationNumberIssuer,
    ) -> None:
        self._realtors = realtors
        self._audit = audit
        self._notifier = notifier
        self._registration_numbers = registration_numbers

    async def review(
        self,
        *,
        user_id: UUID,
        reviewer: CurrentUser,
        action: str,
        reason: str | None,
        reviewer_token: str,
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

        # Before the decision, never after — see the module docstring. The
        # adapter raises RegistrationNumberUnavailable, which the route answers
        # 503 to (it propagates from here untouched), leaving
        # the realtor pending rather than approved-and-unable-to-sign-in.
        registration_number: str | None = None
        if new_status == "approved":
            registration_number = await self._registration_numbers.issue(
                user_id=user_id, bearer_token=reviewer_token
            )

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
            new_value={
                "approval_status": new_status,
                "reason": clean_reason,
                "registration_number": registration_number,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._notify(
            user_id=user_id,
            status=new_status,
            reason=clean_reason,
            registration_number=registration_number,
        )
        return RealtorReviewResult(
            user_id=user_id,
            approval_status=new_status,
            registration_number=registration_number,
        )

    async def _notify(
        self,
        *,
        user_id: UUID,
        status: str,
        reason: str | None,
        registration_number: str | None,
    ) -> None:
        """Best-effort + defensive: a notification failure must never undo a
        committed decision.

        ⚠️ For an approval this message carries the realtor's only copy of their
        registration number, so "best-effort" is doing more work here than it
        does for a reject. That is why the number is also returned to the admin
        UI: a dropped notification is recoverable by a human, an uncommitted
        approval is not.
        """
        try:
            await self._notifier.decision(
                user_id=user_id,
                status=status,
                reason=reason,
                registration_number=registration_number,
            )
        except Exception as exc:  # noqa: BLE001 — never fail a committed decision
            logger.warning(
                "realtor.review.notify_failed",
                extra={"user_id": str(user_id), "status": status, "error": str(exc)},
            )
