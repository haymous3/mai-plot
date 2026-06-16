"""Listing search index adapter (Elasticsearch).

CLAUDE.md non-negotiable: all listing search runs on Elasticsearch, never
Postgres full-text. This adapter mirrors the storage/media adapter shape:

  * SearchIndex — Protocol every call site depends on.
  * ElasticsearchIndex — real adapter (AsyncElasticsearch).
  * InMemorySearchIndex — in-process fake for local + CI, faithfully
    implementing the same query semantics so tests are meaningful without an
    ES cluster.

Only `active`, non-deleted listings are returned by search. The fake's
relevance scoring is intentionally simple (term-overlap) — enough to assert
ordering; the real index uses ES BM25 via multi_match.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchDoc:
    """The indexed representation of a listing — FeedItem fields plus the
    free-text + geo fields search needs."""

    id: UUID
    title: str
    description: str | None
    property_type: str
    state: str
    lga: str
    address_text: str
    lat: float
    lng: float
    size_sqm: Decimal | None
    asking_price_kobo: int
    sale_type: str
    urgency_tag: str | None
    expires_at: datetime | None
    status: str
    doc_verification_status: str
    seller_authority_type: str | None
    view_count: int
    interest_count: int
    created_at: datetime


@dataclass(frozen=True)
class SearchParams:
    q: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None
    state: str | None = None
    lga: str | None = None
    sale_type: str | None = None
    property_type: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    doc_status: str | None = None
    sort: str = "recency"
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class SearchHit:
    doc: SearchDoc
    score: float


class SearchIndex(Protocol):
    async def upsert(self, doc: SearchDoc) -> None:  # pragma: no cover - protocol
        ...

    async def delete(self, listing_id: UUID) -> None:  # pragma: no cover - protocol
        ...

    async def search(
        self, params: SearchParams
    ) -> tuple[list[SearchHit], int]:  # pragma: no cover - protocol
        ...


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _passes_filters(doc: SearchDoc, p: SearchParams) -> bool:
    if doc.status != "active":
        return False
    if p.state and doc.state != p.state:
        return False
    if p.lga and doc.lga != p.lga:
        return False
    if p.sale_type and p.sale_type != "all" and doc.sale_type != p.sale_type:
        return False
    if p.property_type and doc.property_type != p.property_type:
        return False
    if p.price_min is not None and doc.asking_price_kobo < p.price_min:
        return False
    if p.price_max is not None and doc.asking_price_kobo > p.price_max:
        return False
    if p.doc_status == "verified" and doc.doc_verification_status != "verified":
        return False
    if p.lat is not None and p.lng is not None and p.radius_km is not None:
        if _haversine_km(doc.lat, doc.lng, p.lat, p.lng) > p.radius_km:
            return False
    return True


def _text_score(doc: SearchDoc, q: str) -> float:
    """Term-overlap relevance: title hits weigh more than body hits. 0 means
    no match (the doc is dropped when a query is present)."""
    terms = [t for t in q.lower().split() if t]
    if not terms:
        return 0.0
    title = doc.title.lower()
    body = " ".join(
        x.lower() for x in (doc.description or "", doc.address_text, doc.lga, doc.state)
    )
    score = 0.0
    for term in terms:
        if term in title:
            score += 2.0
        elif term in body:
            score += 1.0
    return score


def _urgency_boost(doc: SearchDoc, now: datetime, *, weight: float, scale_days: float) -> float:
    """Relevance boost for a distress listing, weighted by how soon it expires
    (SCRUM-115). Gaussian decay matching the real ES `gauss` function: full
    `weight` at/after expiry, halving every `scale_days` from expiry, →0 far off.
    Normal listings (or distress without an expiry) get 0."""
    if doc.sale_type != "distress" or doc.expires_at is None or scale_days <= 0:
        return 0.0
    days_to_expiry = max(0.0, (doc.expires_at - now).total_seconds() / 86400.0)
    decay: float = 0.5 ** ((days_to_expiry / scale_days) ** 2)
    return weight * decay


def _sort_key(doc: SearchDoc, sort: str) -> tuple[Any, ...]:
    if sort == "price_asc":
        return (doc.asking_price_kobo,)
    if sort == "price_desc":
        return (-doc.asking_price_kobo,)
    if sort == "urgency":
        # distress first, soonest expiry first, then newest.
        expiry = doc.expires_at.timestamp() if doc.expires_at else math.inf
        return (0 if doc.sale_type == "distress" else 1, expiry, -doc.created_at.timestamp())
    # recency (default)
    return (-doc.created_at.timestamp(),)


@dataclass
class InMemorySearchIndex:
    """Test double. Filtering/scoring mirror the real index's semantics."""

    docs: dict[UUID, SearchDoc] | None = None
    urgency_boost_weight: float = 3.0
    urgency_scale_days: float = 7.0

    def __post_init__(self) -> None:
        if self.docs is None:
            self.docs = {}

    async def upsert(self, doc: SearchDoc) -> None:
        assert self.docs is not None
        self.docs[doc.id] = doc

    async def delete(self, listing_id: UUID) -> None:
        assert self.docs is not None
        self.docs.pop(listing_id, None)

    async def search(self, params: SearchParams) -> tuple[list[SearchHit], int]:
        assert self.docs is not None
        now = datetime.now(UTC)
        matches: list[SearchHit] = []
        for doc in self.docs.values():
            if not _passes_filters(doc, params):
                continue
            if params.q:
                score = _text_score(doc, params.q)
                if score <= 0:
                    continue
            else:
                score = 0.0
            matches.append(SearchHit(doc=doc, score=score))

        # Explicit price sorts ignore relevance; everything else (text query,
        # default recency, urgency) ranks by score + the distress urgency boost
        # (SCRUM-115). For match_all the text score is a uniform 0, so the boost
        # alone floats soon-to-expire distress above normal listings; ties break
        # by recency. Mirrors the real ES function_score path.
        if params.sort in ("price_asc", "price_desc"):
            matches.sort(key=lambda h: _sort_key(h.doc, params.sort))
        else:
            matches.sort(key=lambda h: (-self._relevance(h, now), -h.doc.created_at.timestamp()))

        total = len(matches)
        start = (params.page - 1) * params.page_size
        return matches[start : start + params.page_size], total

    def _relevance(self, hit: SearchHit, now: datetime) -> float:
        return hit.score + _urgency_boost(
            hit.doc,
            now,
            weight=self.urgency_boost_weight,
            scale_days=self.urgency_scale_days,
        )


class ElasticsearchIndex:
    """Real adapter over AsyncElasticsearch. Untested in CI (no cluster there);
    its query shape mirrors InMemorySearchIndex. The index + mapping are
    created lazily on first upsert."""

    def __init__(
        self,
        *,
        url: str,
        index: str,
        urgency_boost_weight: float = 3.0,
        urgency_scale_days: float = 7.0,
    ) -> None:
        from elasticsearch import AsyncElasticsearch

        self._index = index
        self._client = AsyncElasticsearch(hosts=[url])
        self._ensured = False
        self._urgency_boost_weight = urgency_boost_weight
        self._urgency_scale_days = urgency_scale_days

    async def _ensure_index(self) -> None:
        if self._ensured:
            return
        if not await self._client.indices.exists(index=self._index):
            await self._client.indices.create(
                index=self._index,
                mappings={
                    "properties": {
                        "title": {"type": "text"},
                        "description": {"type": "text"},
                        "address_text": {"type": "text"},
                        "lga": {"type": "keyword"},
                        "state": {"type": "keyword"},
                        "property_type": {"type": "keyword"},
                        "sale_type": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "doc_verification_status": {"type": "keyword"},
                        "asking_price_kobo": {"type": "long"},
                        "location": {"type": "geo_point"},
                        "created_at": {"type": "date"},
                        "expires_at": {"type": "date"},
                    }
                },
            )
        self._ensured = True

    async def upsert(self, doc: SearchDoc) -> None:
        await self._ensure_index()
        await self._client.index(index=self._index, id=str(doc.id), document=_to_source(doc))

    async def delete(self, listing_id: UUID) -> None:
        await self._client.delete(index=self._index, id=str(listing_id), ignore=[404])  # type: ignore[call-arg]

    async def search(self, params: SearchParams) -> tuple[list[SearchHit], int]:
        await self._ensure_index()
        filters: list[dict[str, Any]] = [{"term": {"status": "active"}}]
        if params.state:
            filters.append({"term": {"state": params.state}})
        if params.lga:
            filters.append({"term": {"lga": params.lga}})
        if params.sale_type and params.sale_type != "all":
            filters.append({"term": {"sale_type": params.sale_type}})
        if params.property_type:
            filters.append({"term": {"property_type": params.property_type}})
        if params.doc_status == "verified":
            filters.append({"term": {"doc_verification_status": "verified"}})
        price_range: dict[str, int] = {}
        if params.price_min is not None:
            price_range["gte"] = params.price_min
        if params.price_max is not None:
            price_range["lte"] = params.price_max
        if price_range:
            filters.append({"range": {"asking_price_kobo": price_range}})
        if params.lat is not None and params.lng is not None and params.radius_km is not None:
            filters.append(
                {
                    "geo_distance": {
                        "distance": f"{params.radius_km}km",
                        "location": {"lat": params.lat, "lon": params.lng},
                    }
                }
            )

        # Explicit price sorts bypass relevance scoring; everything else (text
        # query, default recency, urgency) ranks by _score and gets the distress
        # urgency boost (SCRUM-115).
        price_sort = params.sort in ("price_asc", "price_desc") and not params.q
        if params.q:
            must: dict[str, Any] = {
                "multi_match": {
                    "query": params.q,
                    "fields": ["title^2", "description", "address_text", "lga", "state"],
                }
            }
        else:
            must = {"match_all": {}}

        bool_query: dict[str, Any] = {"bool": {"must": must, "filter": filters}}
        if price_sort:
            query: dict[str, Any] = bool_query
            sort: list[Any] = _es_sort(params.sort)
        else:
            query = self._with_urgency_boost(bool_query)
            sort = ["_score", {"created_at": "desc"}]

        resp = await self._client.search(
            index=self._index,
            query=query,
            sort=sort,
            from_=(params.page - 1) * params.page_size,
            size=params.page_size,
        )
        hits = [
            SearchHit(doc=_from_source(h["_source"]), score=float(h.get("_score") or 0.0))
            for h in resp["hits"]["hits"]
        ]
        total = int(resp["hits"]["total"]["value"])
        return hits, total

    def _with_urgency_boost(self, bool_query: dict[str, Any]) -> dict[str, Any]:
        """Wrap a bool query in a function_score that adds the distress urgency
        boost (Gaussian decay over expires_at). boost_mode=sum so the boost is
        ADDED to the base score (BM25, or a uniform 1.0 for match_all) — same
        additive model as the in-memory fake's _relevance()."""
        return {
            "function_score": {
                "query": bool_query,
                "functions": [
                    {
                        "filter": {"term": {"sale_type": "distress"}},
                        "gauss": {
                            "expires_at": {
                                "origin": "now",
                                "scale": f"{self._urgency_scale_days}d",
                                "decay": 0.5,
                            }
                        },
                        "weight": self._urgency_boost_weight,
                    }
                ],
                "boost_mode": "sum",
                "score_mode": "sum",
            }
        }


def _es_sort(sort: str) -> list[Any]:
    if sort == "price_asc":
        return [{"asking_price_kobo": "asc"}]
    if sort == "price_desc":
        return [{"asking_price_kobo": "desc"}]
    return [{"created_at": "desc"}]


def _to_source(doc: SearchDoc) -> dict[str, Any]:
    return {
        "title": doc.title,
        "description": doc.description,
        "property_type": doc.property_type,
        "state": doc.state,
        "lga": doc.lga,
        "address_text": doc.address_text,
        "location": {"lat": doc.lat, "lon": doc.lng},
        "size_sqm": float(doc.size_sqm) if doc.size_sqm is not None else None,
        "asking_price_kobo": doc.asking_price_kobo,
        "sale_type": doc.sale_type,
        "urgency_tag": doc.urgency_tag,
        "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
        "status": doc.status,
        "doc_verification_status": doc.doc_verification_status,
        "seller_authority_type": doc.seller_authority_type,
        "view_count": doc.view_count,
        "interest_count": doc.interest_count,
        "created_at": doc.created_at.isoformat(),
        "listing_id": str(doc.id),
    }


def _from_source(src: dict[str, Any]) -> SearchDoc:
    loc = src.get("location") or {}
    size = src.get("size_sqm")
    expires = src.get("expires_at")
    return SearchDoc(
        id=UUID(src["listing_id"]),
        title=src["title"],
        description=src.get("description"),
        property_type=src["property_type"],
        state=src["state"],
        lga=src["lga"],
        address_text=src["address_text"],
        lat=float(loc.get("lat", 0.0)),
        lng=float(loc.get("lon", 0.0)),
        size_sqm=Decimal(str(size)) if size is not None else None,
        asking_price_kobo=int(src["asking_price_kobo"]),
        sale_type=src["sale_type"],
        urgency_tag=src.get("urgency_tag"),
        expires_at=datetime.fromisoformat(expires) if expires else None,
        status=src["status"],
        doc_verification_status=src["doc_verification_status"],
        seller_authority_type=src.get("seller_authority_type"),
        view_count=int(src["view_count"]),
        interest_count=int(src["interest_count"]),
        created_at=datetime.fromisoformat(src["created_at"]),
    )


def build_search_index(
    *,
    use_fake: bool,
    url: str,
    index: str,
    urgency_boost_weight: float = 3.0,
    urgency_scale_days: float = 7.0,
) -> SearchIndex:
    """Factory — in-memory fake for local/CI, real Elasticsearch in production."""
    if use_fake:
        return InMemorySearchIndex(
            urgency_boost_weight=urgency_boost_weight,
            urgency_scale_days=urgency_scale_days,
        )
    return ElasticsearchIndex(
        url=url,
        index=index,
        urgency_boost_weight=urgency_boost_weight,
        urgency_scale_days=urgency_scale_days,
    )
