"""Loan application workflow (SCRUM-75).

A buyer applies for a soft loan against their deal. We authorise the applicant,
enforce the 50%-of-agreed-price cap (CLAUDE.md §8) + the partner's loan band and
tenure bounds + the per-buyer daily cap, record the loan (idempotent), and submit
it to the bank partner via the adapter. No money moves here; the bank decision is
async (a later webhook, SCRUM-77).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.adapters.bank import BankAdapterRegistry, BankApplication
from app.repositories.bank_partner_repo import BankPartnerRepository
from app.repositories.loan_repo import LoanRepository, LoanRow
from app.repositories.transaction_repo import TransactionRepository
from app.security import CurrentUser


class LoanApplicationError(RuntimeError):
    pass


class TransactionNotFound(LoanApplicationError):
    pass


class NotTransactionBuyer(LoanApplicationError):
    """Only the deal's buyer may apply for its loan."""


class LoanCapExceeded(LoanApplicationError):
    """Requested amount exceeds 50% of the agreed price."""


class BankPartnerUnavailable(LoanApplicationError):
    """No such active bank partner."""


class LoanBandViolation(LoanApplicationError):
    """Amount is outside the partner's min/max loan band."""


class TenureViolation(LoanApplicationError):
    """Tenure is outside the partner's min/max months."""


class DailyLimitReached(LoanApplicationError):
    """The buyer has hit the per-day application cap."""


@dataclass(frozen=True)
class LoanApplicationResult:
    loan_id: UUID
    status: str
    bank_reference_id: str | None
    requested_amount_kobo: int


class LoanApplicationService:
    def __init__(
        self,
        *,
        transactions: TransactionRepository,
        partners: BankPartnerRepository,
        loans: LoanRepository,
        registry: BankAdapterRegistry,
        loan_cap_bps: int,
        max_applications_per_day: int,
    ) -> None:
        self._transactions = transactions
        self._partners = partners
        self._loans = loans
        self._registry = registry
        self._loan_cap_bps = loan_cap_bps
        self._max_per_day = max_applications_per_day

    async def apply(
        self,
        *,
        buyer: CurrentUser,
        transaction_id: UUID,
        bank_partner_id: UUID,
        requested_amount_kobo: int,
        tenure_months: int,
        idempotency_key: UUID,
    ) -> LoanApplicationResult:
        # Idempotent retry — return the existing application untouched.
        existing = await self._loans.get_by_idempotency(buyer.user_id, idempotency_key)
        if existing is not None:
            return self._result(existing)

        txn = await self._transactions.get(transaction_id)
        if txn is None:
            raise TransactionNotFound()
        if txn.buyer_id != buyer.user_id:
            raise NotTransactionBuyer()

        cap = txn.agreed_price_kobo * self._loan_cap_bps // 10_000
        if requested_amount_kobo > cap:
            raise LoanCapExceeded()

        partner = await self._partners.get_active(bank_partner_id)
        if partner is None:
            raise BankPartnerUnavailable()
        if not (partner.loan_min_kobo <= requested_amount_kobo <= partner.loan_max_kobo):
            raise LoanBandViolation()
        if not (partner.min_tenure_months <= tenure_months <= partner.max_tenure_months):
            raise TenureViolation()

        if await self._loans.count_today(buyer.user_id) >= self._max_per_day:
            raise DailyLimitReached()

        loan_id, created = await self._loans.create(
            buyer_id=buyer.user_id,
            transaction_id=transaction_id,
            bank_partner_id=bank_partner_id,
            requested_amount_kobo=requested_amount_kobo,
            tenure_months=tenure_months,
            idempotency_key=idempotency_key,
        )
        if not created:  # raced with a concurrent identical apply
            row = await self._loans.get(loan_id)
            assert row is not None
            return self._result(row)

        adapter = self._registry.for_partner(short_code=partner.short_code)
        submission = await adapter.submit_application(
            BankApplication(
                loan_id=loan_id,
                buyer_id=buyer.user_id,
                transaction_id=transaction_id,
                requested_amount_kobo=requested_amount_kobo,
                tenure_months=tenure_months,
            )
        )
        await self._loans.set_bank_reference(
            loan_id, bank_reference_id=submission.bank_reference_id, status=submission.status
        )
        return LoanApplicationResult(
            loan_id=loan_id,
            status=submission.status,
            bank_reference_id=submission.bank_reference_id,
            requested_amount_kobo=requested_amount_kobo,
        )

    async def list_for_buyer(self, buyer: CurrentUser) -> list[LoanRow]:
        return await self._loans.list_for_buyer(buyer.user_id)

    @staticmethod
    def _result(row: LoanRow) -> LoanApplicationResult:
        return LoanApplicationResult(
            loan_id=row.id,
            status=row.status,
            bank_reference_id=row.bank_reference_id,
            requested_amount_kobo=row.requested_amount_kobo,
        )
