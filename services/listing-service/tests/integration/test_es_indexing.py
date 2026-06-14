"""Elasticsearch indexing & sync integration tests (SCRUM-54).

Runs ListingIndexSync against Postgres + the in-memory index fake (CI has no
ES cluster). Covers the two behaviours the unit tests can't prove end-to-end:
the es_indexed_at stamp is written to the DB, and a listing that leaves an
indexable status is removed from the index.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.search_index import InMemorySearchIndex
from app.config import get_settings
from app.repositories.listing_repo import ListingRepository
from app.services.listing_index_sync import ListingIndexSync


async def _sync(listing_id: UUID, index: InMemorySearchIndex) -> str:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            action = await ListingIndexSync(index=index, listings=ListingRepository(session)).sync(
                listing_id
            )
            await session.commit()
            return action
    finally:
        await engine.dispose()


def _es_indexed_at(db_engine: Engine, listing_id: UUID) -> Any:
    with db_engine.connect() as conn:
        return conn.execute(
            text("SELECT es_indexed_at FROM property_listings WHERE id = :id"),
            {"id": listing_id},
        ).scalar_one()


@pytest.mark.asyncio
async def test_create_endpoint_stamps_es_indexed_at(
    clean_listing_tables: None,
    disable_cache: None,
    search_index_fake: Any,
    http_client: AsyncClient,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    mint_access_token: Callable[[UUID, str], str],
    auth_header: Callable[[str], dict[str, str]],
) -> None:
    seller = seed_seller(phone="08012345678")
    token = mint_access_token(seller, "seller")
    body = {
        "title": "Indexed Plot",
        "property_type": "land",
        "address_text": "1 Demo St",
        "location": {"lat": 6.5, "lng": 3.4},
        "lga": "Ikeja",
        "state": "Lagos",
        "asking_price_kobo": 5_000_000_000,
        "sale_type": "normal",
    }
    create = await http_client.post("/listings", json=body, headers=auth_header(token))
    assert create.status_code == 201, create.text
    listing_id = UUID(create.json()["listing_id"])

    # Inline dispatch synced the doc and stamped es_indexed_at on the row.
    assert listing_id in search_index_fake.docs
    assert _es_indexed_at(db_engine, listing_id) is not None


def _in_index(index: InMemorySearchIndex, listing_id: UUID) -> bool:
    assert index.docs is not None
    return listing_id in index.docs


@pytest.mark.asyncio
async def test_sync_upserts_then_removes_on_expire(
    clean_listing_tables: None,
    db_engine: Engine,
    seed_seller: Callable[..., UUID],
    seed_listing: Callable[..., UUID],
) -> None:
    seller = seed_seller(phone="08087654321")
    listing_id = seed_listing(seller_id=seller, status="active", title="Live Plot")
    index = InMemorySearchIndex()

    # Active -> upserted and present.
    assert await _sync(listing_id, index) == "upserted"
    assert _in_index(index, listing_id)
    assert _es_indexed_at(db_engine, listing_id) is not None

    # Status leaves the indexable set -> the doc is removed from the index.
    with db_engine.begin() as conn:
        conn.execute(
            text("UPDATE property_listings SET status = 'expired' WHERE id = :id"),
            {"id": listing_id},
        )
    assert await _sync(listing_id, index) == "deleted"
    assert not _in_index(index, listing_id)
