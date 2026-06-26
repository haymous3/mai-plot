"""Celery task: advance a transaction on a bank loan decision (SCRUM-128).

Public task name `transactions.advance_loan_decision` — loan-service enqueues it
by this stable name on a `loan.decision_ready` webhook. Thin wrapper around
LoanDecisionStageService: builds a fresh async session and runs the (async)
transition inside asyncio.run().

No autoretry: the advance is idempotent (it only fires from 'loan_applied' and is
a no-op otherwise), so a retried webhook is harmless.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.config import get_settings
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.transaction_repo import TransactionRepository
from app.services.loan_stage import LoanDecisionStageService


async def _run(transaction_id: UUID, decision: str) -> str:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            service = LoanDecisionStageService(
                transactions=TransactionRepository(session),
                audit=AuditLogRepository(session),
                actor_id=UUID(settings.disbursement_actor_id),
            )
            result = await service.advance(transaction_id=transaction_id, decision=decision)
            await session.commit()
    finally:
        await engine.dispose()
    return result.outcome.value


@celery_app.task(name="transactions.advance_loan_decision")  # type: ignore[untyped-decorator]
def advance_loan_decision(*, transaction_id: str, decision: str) -> str:
    """Entry point loan-service enqueues. Returns the advance outcome."""
    return asyncio.run(_run(UUID(transaction_id), decision))
