"""Admin audit-log viewer endpoint (SCRUM-126).

GET /admin/analytics/audit-log — paginated, filterable, newest-first. Gated by
require_admin (admin JWT + IP allowlist). Read-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_audit_query_service, require_admin
from app.repositories.audit_repo import AuditQuery
from app.schemas.audit import AuditLogListResponse
from app.security import CurrentUser
from app.services.audit_query import AuditQueryService

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ServiceDep = Annotated[AuditQueryService, Depends(get_audit_query_service)]


@router.get("/audit-log", response_model=AuditLogListResponse)
async def audit_log(
    admin: AdminDep,
    service: ServiceDep,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    actor_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> AuditLogListResponse:
    query = AuditQuery(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return await service.list(query=query, page=page, page_size=page_size)
