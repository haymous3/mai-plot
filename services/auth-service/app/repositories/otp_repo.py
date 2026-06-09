"""DB access for otp_codes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OtpCode


class OtpRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, phone: str, code_hash: str, purpose: str, expires_at: datetime
    ) -> UUID:
        otp = OtpCode(phone=phone, code_hash=code_hash, purpose=purpose, expires_at=expires_at)
        self._session.add(otp)
        await self._session.flush()
        return otp.id

    async def get_active(self, *, phone: str, purpose: str) -> OtpCode | None:
        """Return the newest unused OTP for this (phone, purpose), or None."""
        stmt = (
            select(OtpCode)
            .where(
                OtpCode.phone == phone,
                OtpCode.purpose == purpose,
                OtpCode.used_at.is_(None),
            )
            .order_by(OtpCode.created_at.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def mark_used(self, otp_id: UUID) -> None:
        stmt = update(OtpCode).where(OtpCode.id == otp_id).values(used_at=datetime.now(UTC))
        await self._session.execute(stmt)
