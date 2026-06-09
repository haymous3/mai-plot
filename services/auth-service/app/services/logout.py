"""Logout — revoke a refresh token.

The endpoint is authenticated (a valid access token identifies the
caller). Logout revokes the *refresh* token supplied in the body so it
can no longer be rotated. The operation is idempotent and never leaks
whether a token existed: an unknown token, an already-revoked token, or a
token belonging to a different user all return success without changing
state. This keeps logout safe to retry and non-enumerable.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.services.jwt_service import JwtService

logger = logging.getLogger(__name__)


class LogoutService:
    def __init__(
        self,
        *,
        refresh_tokens: RefreshTokenRepository,
        jwt: JwtService,
    ) -> None:
        self._refresh_tokens = refresh_tokens
        self._jwt = jwt

    async def logout(self, *, user_id: UUID, refresh_token: str) -> None:
        stored = await self._refresh_tokens.get_by_hash(self._jwt.hash_token(refresh_token))
        # Only revoke a token that exists and actually belongs to the
        # caller — never let one user revoke another's session.
        if stored is not None and stored.user_id == user_id:
            await self._refresh_tokens.revoke(stored.id)

        logger.info("logout.ok", extra={"user_id": str(user_id)})
