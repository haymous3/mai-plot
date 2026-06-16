"""/admin route handlers — legal-team PoA review queue (SCRUM-56).

Every endpoint here is gated by `require_legal_team` (legal_team JWT + IP
allowlist). Handlers stay thin: build the request, call the service, map domain
errors to the api-contracts.md envelope. No DB calls here.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    get_poa_queue_service,
    get_poa_review_service,
    require_legal_team,
)
from app.schemas.admin import (
    Pagination,
    PoaQueueItem,
    PoaQueueResponse,
    PoaReviewRequest,
    PoaReviewResponse,
)
from app.security import CurrentUser
from app.services.poa_queue import PoaQueueService
from app.services.poa_review import (
    PoaNotPending,
    PoaReviewService,
    PoaTargetNotFound,
    ReasonRequired,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": {}},
    )


@router.get("/poa/queue", response_model=PoaQueueResponse)
async def poa_queue(
    _: Annotated[CurrentUser, Depends(require_legal_team)],
    service: Annotated[PoaQueueService, Depends(get_poa_queue_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PoaQueueResponse:
    result = await service.list_pending(page=page, page_size=page_size)
    return PoaQueueResponse(
        items=[PoaQueueItem.model_validate(row) for row in result.items],
        pagination=Pagination(page=result.page, page_size=result.page_size, total=result.total),
    )


@router.post("/poa/{user_id}/review", response_model=PoaReviewResponse)
async def poa_review(
    user_id: UUID,
    body: PoaReviewRequest,
    request: Request,
    caller: Annotated[CurrentUser, Depends(require_legal_team)],
    service: Annotated[PoaReviewService, Depends(get_poa_review_service)],
) -> PoaReviewResponse | JSONResponse:
    client_ip = request.client.host if request.client else None
    try:
        result = await service.review(
            user_id=user_id,
            reviewer=caller,
            action=body.action,
            reason=body.reason,
            ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
    except PoaTargetNotFound:
        return _error(
            status.HTTP_404_NOT_FOUND,
            "POA_TARGET_NOT_FOUND",
            "No PoA submission found for this user.",
        )
    except PoaNotPending:
        return _error(
            status.HTTP_409_CONFLICT,
            "POA_NOT_PENDING",
            "This PoA submission is not awaiting review.",
        )
    except ReasonRequired:
        # Literal 422 sidesteps the status.HTTP_422_* deprecation rename.
        return _error(422, "POA_REASON_REQUIRED", "A rejection reason is required.")

    return PoaReviewResponse(user_id=result.user_id, poa_verified_status=result.poa_verified_status)
