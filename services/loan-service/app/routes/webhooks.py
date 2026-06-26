"""Bank decision webhook (SCRUM-76). POST /webhooks/bank — public, HMAC-verified.

Kong routes /webhooks/bank with NO jwt plugin; authenticity is the
x-bank-signature HMAC verified here (review.md §5). Returns 200 for every
business outcome (decided / duplicate / ignored / unknown_loan) so the bank
doesn't retry on a no-op; only a bad signature (401) or unparseable body (400)
is an error.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_loan_decision_service
from app.services.loan_decision import LoanDecisionWebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

ServiceDep = Annotated[LoanDecisionWebhookService, Depends(get_loan_decision_service)]


@router.post("/bank")
async def bank_webhook(request: Request, service: ServiceDep) -> JSONResponse:
    raw = await request.body()
    signature = request.headers.get("x-bank-signature")
    if not service.verify_signature(raw, signature):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "error_code": "INVALID_SIGNATURE",
                "message": "Webhook signature verification failed.",
                "details": {},
            },
        )
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error_code": "INVALID_PAYLOAD",
                "message": "Body is not JSON.",
                "details": {},
            },
        )

    outcome = await service.handle(payload)
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": outcome.value})
