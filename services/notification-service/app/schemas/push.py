"""Schemas for Web Push subscription management (SCRUM-79).

Shapes mirror the browser PushSubscription.toJSON() — `{endpoint, keys:{p256dh,
auth}}` — so the frontend can POST the subscription object near-verbatim.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushKeys


class PushSubscriptionResponse(BaseModel):
    id: UUID


class PushUnsubscribeRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)
