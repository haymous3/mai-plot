"""Integration tests for commission accrual + summary (SCRUM-74)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.repositories.commission_repo import CommissionRepository
from app.services.commission_service import CommissionService

pytestmark = pytest.mark.asyncio


async def _accrue() -> None:
    """Run the accrual job once against the test DB (the beat task's logic)."""
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = CommissionService(
                commissions=CommissionRepository(session), rate_bps=200, available_business_days=3
            )
            await service.accrue()
            await session.commit()
    finally:
        await engine.dispose()


def _seed_completed_deal(db_engine: Engine, *, realtor: UUID, price: int = 5_000_000_000) -> UUID:
    """A completed transaction + a completed inspection by `realtor`."""
    listing_id, tx_id, inspection_id = uuid4(), uuid4(), uuid4()
    buyer, seller = uuid4(), uuid4()
    past = datetime.now(UTC) - timedelta(days=1)
    with db_engine.begin() as conn:
        for uid, role in ((buyer, "buyer"), (seller, "seller")):
            conn.execute(
                text(
                    "INSERT INTO users (id, role, verified_status, is_active) "
                    "VALUES (:id, :role, 'id_verified', TRUE)"
                ),
                {"id": uid, "role": role},
            )
        conn.execute(
            text(
                "INSERT INTO transactions (id, listing_id, buyer_id, seller_id, "
                "agreed_price_kobo, stage) VALUES (:id, :lid, :bid, :sid, :price, 'completed')"
            ),
            {"id": tx_id, "lid": listing_id, "bid": buyer, "sid": seller, "price": price},
        )
        conn.execute(
            text(
                """
                INSERT INTO inspections
                    (id, transaction_id, realtor_id, proposed_date, confirmed_date,
                     status, assignment_expires_at)
                VALUES (:id, :tx, :realtor, :past, :past, 'completed', :past)
                """
            ),
            {"id": inspection_id, "tx": tx_id, "realtor": realtor, "past": past},
        )
    return tx_id


async def test_accrual_records_commission_then_summary(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    _seed_completed_deal(db_engine, realtor=realtor)

    await _accrue()

    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT amount_kobo, status FROM commissions WHERE realtor_id = :r"),
            {"r": realtor},
        ).first()
        assert row is not None
        assert row.amount_kobo == 100_000_000  # 2% of ₦50,000,000
        assert row.status == "pending"  # held 3 business days

    summary = await http_client.get(
        "/realtors/me/commission", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert summary.status_code == 200
    assert summary.json() == {
        "pending_kobo": 100_000_000,
        "available_kobo": 0,
        "withdrawn_kobo": 0,
    }


async def test_accrual_is_idempotent(
    clean_tables: None,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
) -> None:
    realtor = seed_user(role="realtor")
    _seed_completed_deal(db_engine, realtor=realtor)

    await _accrue()
    await _accrue()  # second run records nothing new

    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) AS n FROM commissions WHERE realtor_id = :r"), {"r": realtor}
        ).scalar_one()
        assert count == 1


async def test_release_makes_due_commission_available(
    clean_tables: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_user: Callable[..., UUID],
    mint_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    realtor = seed_user(role="realtor")
    past = datetime.now(UTC) - timedelta(hours=1)
    with db_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO commissions
                    (realtor_id, transaction_id, inspection_id, amount_kobo, rate_bps,
                     status, available_at)
                VALUES (:r, :tx, :insp, 100000000, 200, 'pending', :past)
                """
            ),
            {"r": realtor, "tx": uuid4(), "insp": uuid4(), "past": past},
        )

    await _accrue()  # release_due flips the now-due commission

    summary = await http_client.get(
        "/realtors/me/commission", headers=auth_header(mint_token(realtor, "realtor"))
    )
    assert summary.json()["available_kobo"] == 100_000_000
    assert summary.json()["pending_kobo"] == 0
