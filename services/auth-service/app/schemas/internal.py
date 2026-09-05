"""Request/response models for the /internal endpoints (SCRUM-207).

Kept out of schemas/auth.py because nothing public serves these — see
app/routes/internal.py for why they are not routed through Kong.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class RegistrationNumberResponse(BaseModel):
    """The realtor's Maihomme registration number.

    `newly_issued` is false when the realtor already had one, so a caller
    retrying a half-failed approval can tell a fresh issuance from a no-op —
    and knows the email it is about to send repeats a number the realtor may
    already have.
    """

    user_id: UUID
    registration_number: str
    newly_issued: bool
