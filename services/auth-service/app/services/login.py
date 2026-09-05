"""Password login, by email address or by Maihomme registration number.

Returns the same access+refresh pair as OTP verification. A single generic
error (InvalidCredentials) covers every failure — unknown identifier, no
password set, wrong password, and "this realtor must use their registration
number" — never revealing which, to avoid account enumeration.

Two identifiers, one endpoint (SCRUM-207)
-----------------------------------------
Buyers, sellers and admins sign in with their email. An APPROVED realtor signs
in with the `MH-R-…` number the platform issued and emailed them at approval,
because that is the identifier the product hands them. The identifier is
resolved by shape — an `@` means email — so the client sends one field.

⚠️ Email is refused for a realtor **who has a number**, not for realtors as a
class. The distinction is what keeps the flow whole: an application awaiting
review, or one that was rejected and needs re-submitting, has no number yet,
and refusing those would lock a realtor out of the very screen that tells them
so. The refusal is silent (the same INVALID_CREDENTIALS as a wrong password) —
a distinct "use your registration number" error would confirm to a stranger
that an email address belongs to an approved realtor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import bcrypt

from app.repositories.auth_credentials_repo import AuthCredentialsRepository
from app.repositories.realtor_registration_repo import RealtorRegistrationRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserCore, UserRepository
from app.services.jwt_service import JwtService, TokenPair
from app.services.password import verify_password
from app.services.registration_number import looks_like_email, normalize_registration_number

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
        registration_numbers: RealtorRegistrationRepository,
        jwt: JwtService,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._refresh_tokens = refresh_tokens
        self._registration_numbers = registration_numbers
        self._jwt = jwt

    async def login(self, *, identifier: str, password: str) -> LoginResult:
        user = await self._resolve(identifier)
        if user is None:
            # Run a dummy verify to keep timing similar whether or not the
            # identifier exists (mitigates user enumeration via response time).
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

    async def _resolve(self, identifier: str) -> UserCore | None:
        """The account this identifier signs in, or None if it signs in none.

        None is returned for every "no" — malformed input included — so the
        caller has exactly one failure path and one response.
        """
        candidate = identifier.strip()
        if looks_like_email(candidate):
            user = await self._users.get_active_by_email(candidate)
            if user is None:
                return None
            if user.role == "realtor":
                issued = await self._registration_numbers.get_for_user(user.id)
                if issued is not None:
                    # Approved realtor: the registration number is the only way in.
                    return None
            return user

        number = normalize_registration_number(candidate)
        if number is None:
            return None
        user_id = await self._registration_numbers.get_user_id(number)
        if user_id is None:
            return None
        return await self._users.get_active_by_id(user_id)
