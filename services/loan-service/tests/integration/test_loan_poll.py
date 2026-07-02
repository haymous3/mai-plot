"""Integration tests for the loan-status polling fallback (SCRUM-130).

Exercises LoanRepository.list_pollable + LoanStatusPoller against a real DB. Uses
a negative stale threshold (NOW() + 1min) so just-seeded loans fall inside the
window without needing to back-date created_at. With the fake adapter every poll
reports under_review, so an end-to-end run scans but decides nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.bank import build_bank_adapter_registry
from app.config import get_settings
from app.repositories.loan_repo import LoanRepository
from app.services.loan_decision import LoanDecisionWebhookService
from app.services.loan_status_poller import LoanStatusPoller

pytestmark = pytest.mark.asyncio

# NOW() - make_interval(mins => -1) == NOW() + 1 min, so a just-seeded loan
# (created_at ≈ NOW()) is inside the "older than" window.
_FRESH_OK = -1


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        yield s
    await engine.dispose()


def _partner_short_code(db_engine: Engine, partner_id: UUID) -> str:
    with db_engine.connect() as conn:
        code: str = conn.execute(
            text("SELECT short_code FROM bank_partners WHERE id = :id"), {"id": partner_id}
        ).scalar_one()
    return code


async def test_list_pollable_selects_only_pending_with_reference(
    clean_tables: None,
    db_engine: Engine,
    session: AsyncSession,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    short_code = _partner_short_code(db_engine, partner)

    pending = seed_loan(
        buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-POLL", status="under_review"
    )
    # Decided → excluded.
    seed_loan(buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-DONE", status="approved")
    # Pending but no bank reference yet → excluded (never submitted).
    no_ref = seed_loan(
        buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-NOREF", status="submitted"
    )
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE loans SET bank_reference_id = NULL WHERE id = :id"), {"id": no_ref}
        )

    repo = LoanRepository(session)
    pollable = await repo.list_pollable(older_than_minutes=_FRESH_OK, limit=100)

    ids = {p.loan.id for p in pollable}
    assert ids == {pending}
    item = next(p for p in pollable if p.loan.id == pending)
    assert item.short_code == short_code
    assert item.bank_reference_id == "REF-POLL"


async def test_list_pollable_respects_stale_threshold(
    clean_tables: None,
    session: AsyncSession,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    seed_loan(
        buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-FRESH", status="under_review"
    )

    repo = LoanRepository(session)
    # A just-created loan is NOT yet 30 minutes stale, so the real threshold skips it.
    assert await repo.list_pollable(older_than_minutes=30, limit=100) == []


async def test_poller_run_with_fake_adapter_is_a_noop(
    clean_tables: None,
    session: AsyncSession,
    seed_user: Callable[..., UUID],
    seed_transaction: Callable[..., UUID],
    seed_bank_partner: Callable[..., UUID],
    seed_loan: Callable[..., UUID],
) -> None:
    buyer = seed_user(role="buyer")
    tx = seed_transaction(buyer_id=buyer)
    partner = seed_bank_partner()
    seed_loan(
        buyer_id=buyer, tx_id=tx, partner_id=partner, reference="REF-FAKE", status="under_review"
    )

    settings = get_settings()
    repo = LoanRepository(session)

    class _NullNotifier:
        async def loan_decision(self, **kwargs: object) -> None: ...
        async def title_released(self, **kwargs: object) -> None: ...
        async def account_opened(self, **kwargs: object) -> None: ...
        async def disbursed(self, **kwargs: object) -> None: ...

    class _NullTxTasks:
        def credit_loan_disbursement(self, **kwargs: object) -> None: ...
        def advance_loan_decision(self, **kwargs: object) -> None: ...

    decisions = LoanDecisionWebhookService(
        loans=repo,
        notifier=_NullNotifier(),
        tx_tasks=_NullTxTasks(),
        secret=settings.bank_webhook_secret,
    )
    poller = LoanStatusPoller(
        loans=repo,
        registry=build_bank_adapter_registry(enabled=False, timeout=1.0, retries=0, base_delay=0.0),
        decisions=decisions,
        stale_minutes=_FRESH_OK,
        batch_limit=100,
    )
    result = await poller.run()
    # The fake adapter reports under_review, so the loan is scanned but not decided.
    assert result.scanned == 1
    assert result.decided == 0
    assert result.errors == 0
