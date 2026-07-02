"""Read side for a single loan's detail (SCRUM-94).

Powers the buyer's application status + approval page (GET /loans/{loan_id}).
Buyer-or-admin: a buyer sees only their own loan. Read-only, non-§11.
"""

from __future__ import annotations

from uuid import UUID

from app.repositories.loan_repo import LoanDetailRow, LoanRepository
from app.security import CurrentUser


class LoanNotFound(RuntimeError):
    pass


class NotLoanViewer(RuntimeError):
    """Only the loan's buyer (or an admin) may view it."""


class LoanQueryService:
    def __init__(self, *, loans: LoanRepository) -> None:
        self._loans = loans

    async def get_detail(self, loan_id: UUID, caller: CurrentUser) -> LoanDetailRow:
        loan = await self._loans.get_detail(loan_id)
        if loan is None:
            raise LoanNotFound
        if caller.role != "admin" and loan.buyer_id != caller.user_id:
            raise NotLoanViewer
        return loan
