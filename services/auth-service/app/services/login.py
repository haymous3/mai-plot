"""Email/password login.

Returns the same access+refresh pair as OTP verification. A single
generic error (InvalidCredentials) covers unknown email, no password set,
and wrong password — never reveal which, to avoid account enumeration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import bcrypt

from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.jwt_service import JwtService, TokenPair
from app.services.password import verify_password

logger = logging.getLogger(__name__)

# A real bcrypt hash of a throwaway value, computed once. Verifying against
# it when the account/password is absent spends roughly the same time as a
# genuine check, so response timing doesn't leak whether an email exists.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser-not-a-real-password", bcrypt.gensalt()).decode(
    "utf-8"
)


class LoginError(RuntimeError):
    pass


class InvalidCredentials(LoginError):
    pass


@dataclass(frozen=True)
class LoginResult:
    user_id: UUID
    role: str
    verified_status: str
    tokens: TokenPair


class LoginService:
    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: AuthCredentialsRepository,
        refresh_tokens: RefreshTokenRepository,
        jwt: JwtService,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._refresh_tokens = refresh_tokens
        self._jwt = jwt

    async def login(self, *, email: str, password: str) -> LoginResult:
        user = await self._users.get_active_by_email(email)
        if user is None:
            # Run a dummy verify to keep timing similar whether or not the
            # email exists (mitigates user enumeration via response time).
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentials()

        stored_hash = await self._credentials.get_password_hash(user.id)
        if stored_hash is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentials()

        if not verify_password(password, stored_hash):
            raise InvalidCredentials()

        tokens = self._jwt.issue_pair(user_id=user.id, role=user.role)
        await self._refresh_tokens.create(
            user_id=user.id,
            token_hash=tokens.refresh_token_hash,
            expires_at=tokens.refresh_expires_at,
        )

        logger.info("login.ok", extra={"user_id": str(user.id), "role": user.role})
        return LoginResult(
            user_id=user.id,
            role=user.role,
            verified_status=user.verified_status,
            tokens=tokens,
        )
