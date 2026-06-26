"""Paystack webhook (SCRUM-83). POST /webhooks/paystack — public, HMAC-verified.

Kong routes /webhooks/paystack with NO jwt plugin; authenticity is the
x-paystack-signature HMAC verified here. Returns 200 for every business outcome
(credited / duplicate / ignored / amount_mismatch) so Paystack doesn't retry on a
no-op; only a bad signature (401) or unparseable body (400) is an error.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import get_webhook_service
from app.services.paystack_webhook import PaystackWebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

WebhookServiceDep = Annotated[PaystackWebhookService, Depends(get_webhook_service)]


@router.post("/paystack")
async def paystack_webhook(request: Request, service: WebhookServiceDep) -> JSONResponse:
    raw = await request.body()
    signature = request.headers.get("x-paystack-signature")
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
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error_code": "INVALID_PAYLOAD",
                "message": "Body is not JSON.",
                "details": {},
            },
        )
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
