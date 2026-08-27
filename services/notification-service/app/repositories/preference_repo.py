"""Access to notification_preferences (owned by notification-service, SCRUM-122).

Per-user, per-channel opt-out. A missing row means "all defaults" (everything
enabled) — the opt-out model — so `get` never returns None; it returns the
defaults. Writes upsert the single row per user.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Channels that have a preference flag. in_app is intentionally absent — it's the
# user's notification-centre record and is always written.
_CHANNEL_FLAGS = {"push": "push_enabled", "sms": "sms_enabled", "email": "email_enabled"}


@dataclass(frozen=True)
class NotificationPreferences:
    push_enabled: bool = True
    sms_enabled: bool = True
    email_enabled: bool = True
    # ⚠️ Defaults FALSE while every other flag defaults TRUE, and that
    # asymmetry is deliberate — do NOT "harmonise" it. The three above are
    # transactional (OTP, deal accepted, loan decision) and follow this
    # table's opt-OUT model. Marketing is promotional, and NDPR (§9) requires
    # explicit affirmative consent, so it is opt-IN. Migration 0005 has the
    # full reasoning.
    marketing_enabled: bool = False

    def allows(self, channel: str) -> bool:
        """Whether a channel is enabled. Channels with no flag (in_app) are always
        allowed."""
        flag = _CHANNEL_FLAGS.get(channel)
        if flag is None:
            return True
        value: bool = getattr(self, flag)
        return value


class PreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> NotificationPreferences:
        row = (
            await self._session.execute(
                text(
                    "SELECT push_enabled, sms_enabled, email_enabled, marketing_enabled "
                    "FROM notification_preferences "
                    "WHERE user_id = :uid AND deleted_at IS NULL"
                ),
                {"uid": user_id},
            )
        ).first()
        if row is None:
            return NotificationPreferences()
        return NotificationPreferences(
            push_enabled=row.push_enabled,
            sms_enabled=row.sms_enabled,
            email_enabled=row.email_enabled,
            marketing_enabled=row.marketing_enabled,
        )

    async def update(
        self,
        user_id: UUID,
        *,
        push_enabled: bool | None = None,
        sms_enabled: bool | None = None,
        email_enabled: bool | None = None,
        marketing_enabled: bool | None = None,
    ) -> NotificationPreferences:
        """Upsert the caller's preferences. Only the fields provided are changed;
        omitted fields keep their current (or default) value via COALESCE."""
        await self._session.execute(
            text(
                """
                INSERT INTO notification_preferences
                    (user_id, push_enabled, sms_enabled, email_enabled, marketing_enabled)
                VALUES
                    (:uid, COALESCE(:push, TRUE), COALESCE(:sms, TRUE), COALESCE(:email, TRUE),
                     COALESCE(:marketing, FALSE))
                ON CONFLICT (user_id) DO UPDATE SET
                    push_enabled = COALESCE(:push, notification_preferences.push_enabled),
                    sms_enabled = COALESCE(:sms, notification_preferences.sms_enabled),
                    email_enabled = COALESCE(:email, notification_preferences.email_enabled),
                    marketing_enabled = COALESCE(
                        :marketing, notification_preferences.marketing_enabled),
                    deleted_at = NULL,
                    updated_at = NOW()
                """
            ),
            {
                "uid": user_id,
                "push": push_enabled,
                "sms": sms_enabled,
                "email": email_enabled,
                "marketing": marketing_enabled,
            },
        )
        return await self.get(user_id)
