"""Audit-log query service (SCRUM-126).

Thin orchestration between the route and the read repository (CLAUDE.md: routes
never touch the DB directly). Clamps pagination, runs the count + page queries,
and builds the paginated response.
"""

from __future__ import annotations

from app.repositories.audit_repo import AuditLogReadRepository, AuditQuery
from app.schemas.audit import AuditLogItem, AuditLogListResponse, Pagination


class AuditQueryService:
    def __init__(
        self,
        *,
        repo: AuditLogReadRepository,
        default_page_size: int,
        max_page_size: int,
    ) -> None:
        self._repo = repo
        self._default_page_size = default_page_size
        self._max_page_size = max_page_size

    async def list(
        self, *, query: AuditQuery, page: int, page_size: int | None
    ) -> AuditLogListResponse:
        page = max(1, page)
        size = page_size if page_size is not None else self._default_page_size
        size = min(max(1, size), self._max_page_size)

        total = await self._repo.count(query)
        rows = await self._repo.list(query, limit=size, offset=(page - 1) * size)
        total_pages = (total + size - 1) // size if total else 0

        return AuditLogListResponse(
            items=[AuditLogItem.from_row(r) for r in rows],
            pagination=Pagination(page=page, page_size=size, total=total, total_pages=total_pages),
        )
