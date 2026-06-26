"""FastAPI dependency wiring for loan-service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.bank import BankAdapterRegistry, build_bank_adapter_registry
from app.config import Settings, get_settings
from app.db import get_session
from app.repositories.bank_partner_repo import BankPartnerRepository
from app.repositories.loan_repo import LoanRepository
from app.repositories.repayment_repo import RepaymentMilestoneRepository
from app.repositories.transaction_repo import TransactionRepository
from app.security import AdminAccessError, AuthenticationError, CurrentUser, parse_bearer
from app.services.bank_webhook import BankWebhookDispatcher
from app.services.jwt_verifier import JwtVerifier, TokenExpired, TokenInvalid
from app.services.loan_application import LoanApplicationService
from app.services.loan_decision import LoanDecisionWebhookService
from app.services.loan_disbursement_webhook import LoanDisbursementWebhookService
from app.services.loan_notifier import LoanNotifier, build_loan_notifier
from app.services.loan_repayment import LoanRepaymentWebhookService
from app.services.repayment_query import RepaymentQueryService
from app.services.tx_tasks import TxTaskProducer, build_tx_task_producer

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _jwt_verifier(settings: SettingsDep) -> JwtVerifier:
    return JwtVerifier(secret=settings.jwt_secret, issuer=settings.jwt_issuer)


def _transaction_repo(session: SessionDep) -> TransactionRepository:
    return TransactionRepository(session)


def _bank_partner_repo(session: SessionDep) -> BankPartnerRepository:
    return BankPartnerRepository(session)


def _loan_repo(session: SessionDep) -> LoanRepository:
    return LoanRepository(session)


def _milestone_repo(session: SessionDep) -> RepaymentMilestoneRepository:
    return RepaymentMilestoneRepository(session)


# Process-singleton adapter registry (memoises per-partner adapters).
_registry: BankAdapterRegistry | None = None


def get_bank_registry(settings: SettingsDep) -> BankAdapterRegistry:
    global _registry
    if _registry is None:
        _registry = build_bank_adapter_registry(
            enabled=settings.bank_adapter_enabled,
            timeout=settings.bank_request_timeout_seconds,
            retries=settings.bank_max_retries,
            base_delay=settings.bank_retry_base_delay_seconds,
        )
    return _registry


def get_loan_application_service(
    settings: SettingsDep,
    transactions: Annotated[TransactionRepository, Depends(_transaction_repo)],
    partners: Annotated[BankPartnerRepository, Depends(_bank_partner_repo)],
    loans: Annotated[LoanRepository, Depends(_loan_repo)],
    registry: Annotated[BankAdapterRegistry, Depends(get_bank_registry)],
) -> LoanApplicationService:
    return LoanApplicationService(
        transactions=transactions,
        partners=partners,
        loans=loans,
        registry=registry,
        loan_cap_bps=settings.loan_cap_bps,
        max_applications_per_day=settings.max_loan_applications_per_day,
    )


# Process-singleton loan-decision notifier (Celery producer or no-op).
_notifier: LoanNotifier | None = None


def get_loan_notifier(settings: SettingsDep) -> LoanNotifier:
    global _notifier
    if _notifier is None:
        _notifier = build_loan_notifier(
            enabled=settings.notifications_enabled, broker_url=settings.celery_broker_url
        )
    return _notifier


# Process-singleton tx-service task producer (Celery producer or no-op).
_tx_tasks: TxTaskProducer | None = None


def get_tx_task_producer(settings: SettingsDep) -> TxTaskProducer:
    global _tx_tasks
    if _tx_tasks is None:
        _tx_tasks = build_tx_task_producer(
            enabled=settings.tx_tasks_enabled, broker_url=settings.celery_broker_url
        )
    return _tx_tasks


def get_loan_decision_service(
    settings: SettingsDep,
    loans: Annotated[LoanRepository, Depends(_loan_repo)],
    notifier: Annotated[LoanNotifier, Depends(get_loan_notifier)],
    tx_tasks: Annotated[TxTaskProducer, Depends(get_tx_task_producer)],
) -> LoanDecisionWebhookService:
    return LoanDecisionWebhookService(
        loans=loans, notifier=notifier, tx_tasks=tx_tasks, secret=settings.bank_webhook_secret
    )


def get_loan_disbursement_service(
    loans: Annotated[LoanRepository, Depends(_loan_repo)],
    notifier: Annotated[LoanNotifier, Depends(get_loan_notifier)],
    tx_tasks: Annotated[TxTaskProducer, Depends(get_tx_task_producer)],
) -> LoanDisbursementWebhookService:
    return LoanDisbursementWebhookService(loans=loans, notifier=notifier, tx_tasks=tx_tasks)


def get_loan_repayment_service(
    loans: Annotated[LoanRepository, Depends(_loan_repo)],
    milestones: Annotated[RepaymentMilestoneRepository, Depends(_milestone_repo)],
    notifier: Annotated[LoanNotifier, Depends(get_loan_notifier)],
) -> LoanRepaymentWebhookService:
    return LoanRepaymentWebhookService(loans=loans, milestones=milestones, notifier=notifier)


def get_bank_webhook_dispatcher(
    settings: SettingsDep,
    decision: Annotated[LoanDecisionWebhookService, Depends(get_loan_decision_service)],
    repayment: Annotated[LoanRepaymentWebhookService, Depends(get_loan_repayment_service)],
    disbursement: Annotated[LoanDisbursementWebhookService, Depends(get_loan_disbursement_service)],
) -> BankWebhookDispatcher:
    return BankWebhookDispatcher(
        secret=settings.bank_webhook_secret,
        decision=decision,
        repayment=repayment,
        disbursement=disbursement,
    )


def get_repayment_query_service(
    loans: Annotated[LoanRepository, Depends(_loan_repo)],
    milestones: Annotated[RepaymentMilestoneRepository, Depends(_milestone_repo)],
) -> RepaymentQueryService:
    return RepaymentQueryService(loans=loans, milestones=milestones)


async def get_current_user(
    verifier: Annotated[JwtVerifier, Depends(_jwt_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Validate the bearer access token and return the caller's identity."""
    token = parse_bearer(authorization)
    try:
        claims = verifier.decode_access(token)
    except TokenExpired as exc:
        raise AuthenticationError("TOKEN_EXPIRED", "Access token has expired.") from exc
    except TokenInvalid as exc:
        raise AuthenticationError("TOKEN_INVALID", "Access token is invalid.") from exc

    if claims.role is None:
        raise AuthenticationError("TOKEN_INVALID", "Access token is missing a role.")
    return CurrentUser(user_id=claims.user_id, role=claims.role)


async def require_admin(
    request: Request,
    caller: Annotated[CurrentUser, Depends(get_current_user)],
    settings: SettingsDep,
) -> CurrentUser:
    """Admin gate: a valid admin JWT AND (if configured) a whitelisted IP."""
    if caller.role != "admin":
        raise AdminAccessError("ADMIN_FORBIDDEN", "Admin access required.")
    allowlist = [ip.strip() for ip in settings.admin_ip_allowlist.split(",") if ip.strip()]
    if allowlist:
        client_ip = request.client.host if request.client else None
        if client_ip not in allowlist:
            raise AdminAccessError(
                "ADMIN_IP_FORBIDDEN", "Your IP is not permitted for admin access."
            )
    return caller
