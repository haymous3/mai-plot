"""Schemas for notification preferences (SCRUM-122)."""

from __future__ import annotations

from pydantic import BaseModel


class PreferenceResponse(BaseModel):
    push_enabled: bool
    sms_enabled: bool
    email_enabled: bool
    # Opt-IN, unlike the three above — see migration 0005 and the warning on
    # NotificationPreferences. It is a content category, not a transport: a
    # marketing email would need this AND email_enabled.
    marketing_enabled: bool


class PreferenceUpdate(BaseModel):
    """Partial update — only the channels present are changed (others keep their
    current value)."""

    push_enabled: bool | None = None
    sms_enabled: bool | None = None
    email_enabled: bool | None = None
    marketing_enabled: bool | None = None
