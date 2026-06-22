"""/notifications route handlers — the in-app notification centre (SCRUM-82).

GET lists the caller's feed (keyset paginated, newest-first) with their unread
count; PATCH endpoints mark one or all items read. Handlers are thin: every
query is scoped to the authenticated caller, so users only ever touch their own
notifications.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_notification_centre_service
from app.schemas.notification import (
    MarkAllReadResponse,
    NotificationItem,
    NotificationListResponse,
)
from app.security import CurrentUser
from app.services.cursor import CursorInvalid
from app.services.notification_centre import NotificationCentreService, NotificationNotFound

router = APIRouter(prefix="/notifications", tags=["notifications"])

_MAX_PAGE_SIZE = 100

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
CentreServiceDep = Annotated[NotificationCentreService, Depends(get_notification_centre_service)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    caller: CurrentUserDep,
    service: CentreServiceDep,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = 20,
    cursor: str | None = None,
) -> NotificationListResponse | JSONResponse:
    """Newest-first page of the caller's notifications. The opaque `cursor` (from
    a prior response's next_cursor) resumes the feed; a malformed one is 400. The
    unread count is also surfaced in the X-Unread-Count header for badge UIs."""
    try:
        page = await service.list_notifications(caller.user_id, limit=limit, cursor=cursor)
    except CursorInvalid:
        return _error(status.HTTP_400_BAD_REQUEST, "INVALID_CURSOR", "The cursor is malformed.")
    response.headers["X-Unread-Count"] = str(page.unread_count)
    return NotificationListResponse(
        items=[NotificationItem.from_row(row) for row in page.items],
        next_cursor=page.next_cursor,
        unread_count=page.unread_count,
    )


@router.patch("/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    caller: CurrentUserDep,
    service: CentreServiceDep,
) -> MarkAllReadResponse:
    marked = await service.mark_all_read(caller.user_id)
    return MarkAllReadResponse(marked_read=marked)


@router.patch("/{notification_id}/read", response_model=None)
async def mark_read(
    notification_id: UUID,
    caller: CurrentUserDep,
    service: CentreServiceDep,
) -> Response | JSONResponse:
    """Mark one notification read. 204 on success; 404 if it isn't the caller's
    (or doesn't exist). Idempotent on an already-read item. The 204 is returned
    via an explicit Response — FastAPI forbids declaring a 204 status_code on a
    route that can also return a body (the 404 envelope)."""
    try:
        await service.mark_read(notification_id, user_id=caller.user_id)
    except NotificationNotFound:
        return _error(status.HTTP_404_NOT_FOUND, "NOTIFICATION_NOT_FOUND", "No notification found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
