"""/notifications/push routes — Web Push subscription management (SCRUM-79).

A signed-in user registers (or refreshes) the browser PushSubscription their
Service Worker produced, and can unregister it. Everything is scoped to the
authenticated caller, so a user only ever touches their own subscriptions. The
actual push delivery is a background concern (see notification_dispatch / the
push Celery task) — these endpoints only manage the subscription rows.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse

from app.dependencies import get_current_user, get_push_subscription_repo
from app.repositories.push_subscription_repo import PushSubscriptionRepository
from app.schemas.push import (
    PushSubscriptionCreate,
    PushSubscriptionResponse,
    PushUnsubscribeRequest,
)
from app.security import CurrentUser

router = APIRouter(prefix="/notifications/push", tags=["push"])

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
SubscriptionRepoDep = Annotated[PushSubscriptionRepository, Depends(get_push_subscription_repo)]


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.post(
    "/subscriptions",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_subscription(
    payload: PushSubscriptionCreate,
    caller: CurrentUserDep,
    repo: SubscriptionRepoDep,
) -> PushSubscriptionResponse:
    """Store (or refresh) the caller's browser push subscription. Idempotent on
    (user, endpoint): re-registering the same browser updates its keys and
    revives it if it had been pruned."""
    subscription_id = await repo.upsert(
        user_id=caller.user_id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    return PushSubscriptionResponse(id=subscription_id)


@router.delete("/subscriptions", response_model=None)
async def unregister_subscription(
    payload: PushUnsubscribeRequest,
    caller: CurrentUserDep,
    repo: SubscriptionRepoDep,
) -> Response | JSONResponse:
    """Unsubscribe the caller's browser. 204 on success; 404 if no active
    subscription with that endpoint belongs to the caller (FastAPI forbids a 204
    status_code on a route that can also return the 404 body, so the 204 is an
    explicit Response)."""
    removed = await repo.soft_delete_by_endpoint(user_id=caller.user_id, endpoint=payload.endpoint)
    if not removed:
        return _error(
            status.HTTP_404_NOT_FOUND,
            "PUSH_SUBSCRIPTION_NOT_FOUND",
            "No active push subscription found for that endpoint.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
