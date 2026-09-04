"""Inspection report review (SCRUM-205) — an admin approves or rejects a
submitted report.

Before this, a realtor submitted a report and it sat there: no reviewed state,
no feedback, no way back. The report is the trust artefact the buyer-facing copy
leans on (CLAUDE.md §8), so somebody has to check it.

Product decisions recorded on the ticket:

* Reviewers are the same as for documents — `require_admin`, i.e. the `admin`
  role plus the IP allowlist. `legal_team` is a different gate and guards PoA.
* A rejection does NOT move the inspection off 'completed'. `report_review_status`
  carries the meaning; reverting the inspection status would re-open the
  report-submittable gate in a way that fights the confirmed-date guard.
* Review is not a visibility gate — buyer and seller still read any submitted
  report, reviewed or not.

Every decision writes an append-only audit_log row and notifies the realtor
best-effort, mirroring RealtorReviewService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.repositories.audit_repo import AuditLogRepository
from app.repositories.inspection_repo import InspectionRepository, ReportReviewRow
from app.security import CurrentUser
from app.services.realtor_notifier import RealtorNotifier

logger = logging.getLogger(__name__)

# action -> the review status it writes
_DECISIONS = {"approve": "approved", "reject": "rejected"}
_NOTE_REQUIRED = {"reject"}


class ReportReviewError(RuntimeError):
    pass


class ReportNotFound(ReportReviewError):
    """No inspection with that id, or it has no submitted report."""


class ReportNotPending(ReportReviewError):
    """The report has already been decided, or was never submitted. Also what a
    second admin gets when two decide at once — the guarded UPDATE lets exactly
    one win."""


class ReviewNoteRequired(ReportReviewError):
    """Rejecting must say why: that note is the only thing telling the realtor
    what to fix, and it is what the Report History card shows them."""


@dataclass(frozen=True)
class ReportReviewResult:
    inspection_id: UUID
    report_review_status: str


class ReportReviewService:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        audit: AuditLogRepository,
        notifier: RealtorNotifier,
    ) -> None:
        self._inspections = inspections
        self._audit = audit
        self._notifier = notifier

    async def queue(
        self, *, status: str | None = "pending", limit: int = 100
    ) -> list[ReportReviewRow]:
        """Submitted reports for the admin queue, oldest first."""
        return await self._inspections.list_report_reviews(status=status, limit=limit)

    async def review(
        self,
        *,
        inspection_id: UUID,
        reviewer: CurrentUser,
        action: str,
        note: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> ReportReviewResult:
        decision = _DECISIONS[action]

        inspection = await self._inspections.get(inspection_id)
        if inspection is None or inspection.report_submitted_at is None:
            raise ReportNotFound()
        if inspection.report_review_status != "pending":
            raise ReportNotPending()

        clean_note: str | None = None
        if action in _NOTE_REQUIRED:
            if not note or not note.strip():
                raise ReviewNoteRequired()
            clean_note = note.strip()
        elif note and note.strip():
            # An approval may carry a note; it is optional and shown as feedback.
            clean_note = note.strip()

        applied = await self._inspections.record_report_review(
            inspection_id,
            decision=decision,
            reviewer_id=reviewer.user_id,
            note=clean_note,
        )
        if not applied:
            # Lost the race to another admin between the read and the UPDATE.
            raise ReportNotPending()

        await self._audit.record(
            actor_id=reviewer.user_id,
            actor_role=reviewer.role,
            action=f"inspection.report_{decision}",
            entity_type="inspection",
            entity_id=inspection_id,
            # The row really was 'pending' — the guarded UPDATE proved it, so
            # this is observed history, not an assumption (the SCRUM-192 trap).
            old_value={"report_review_status": "pending"},
            new_value={
                "report_review_status": decision,
                "note": clean_note,
                "revision": inspection.report_revision,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self._notify(
            user_id=inspection.realtor_id,
            inspection_id=inspection_id,
            status=decision,
            note=clean_note,
        )
        return ReportReviewResult(inspection_id=inspection_id, report_review_status=decision)

    async def _notify(
        self, *, user_id: UUID, inspection_id: UUID, status: str, note: str | None
    ) -> None:
        """Best-effort: a notification failure must never undo a committed
        decision."""
        try:
            await self._notifier.report_decision(
                user_id=user_id, inspection_id=inspection_id, status=status, note=note
            )
        except Exception as exc:  # noqa: BLE001 — never fail a committed decision
            logger.warning(
                "inspection.report_review.notify_failed",
                extra={
                    "inspection_id": str(inspection_id),
                    "status": status,
                    "error": str(exc),
                },
            )
