"""view_count increment integration test (SCRUM-114).

With view_count_via_celery default off, the detail GET increments inline
against the request session (CI has no broker), so the effect is observable in
the DB right after the request. In production the same bump runs in a Celery
worker off the request path.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _view_count(db_engine: Engine, listing_id: UUID) -> int:
    with db_engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT view_count FROM property_listings WHERE id = :id"),
                {"id": listing_id},
            ).scalar_one()
        )


@pytest.mark.asyncio
async def test_detail_view_increments_view_count(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    seller = seed_seller(phone="08012345678")
    listing_id = seed_listing(seller_id=seller, status="active")
    assert _view_count(db_engine, listing_id) == 0

    first = await http_client.get(f"/listings/{listing_id}")
    assert first.status_code == 200, first.text
    assert _view_count(db_engine, listing_id) == 1

    # A second view counts again (approximate analytics, no dedup).
    await http_client.get(f"/listings/{listing_id}")
    assert _view_count(db_engine, listing_id) == 2


@pytest.mark.asyncio
async def test_missing_listing_does_not_count(
    clean_listing_tables: None,
    disable_cache: None,
    http_client: AsyncClient,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
    db_engine: Engine,
) -> None:
    # A 404 must not bump anything (nothing to bump) and must not error.
    seller = seed_seller(phone="08012345678")
    other = seed_listing(seller_id=seller, status="active")
    from uuid import uuid4

    response = await http_client.get(f"/listings/{uuid4()}")
    assert response.status_code == 404
    assert _view_count(db_engine, other) == 0  # unrelated listing untouched
