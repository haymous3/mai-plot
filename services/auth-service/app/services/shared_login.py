"""One sign-in for a person's buyer and seller accounts (SCRUM-236).

A person who both buys and sells has ONE email and ONE password. Signing in
lands them on their buyer account; from there they switch to their seller
account and back. Each role is still its own `users` row, because every other
service keys its data by user_id — listings by seller, offers by buyer, PoA
state on the row — and a switch is simply a token pair for the other row.

The rows are tied together by `users.shares_login_with_user_id` (migration
0020): a sharer points at the LOGIN OWNER, the row that holds the email and the
password. One hop, like SCRUM-225's identity link, so a group is one query.

Adding a role
-------------
Only a SIGNED-IN person can add a role, and being signed in is the proof of
ownership. That is what lets this skip the whole registration form: name,
phone, address and verified identity are the same person's and are copied from
the account they are already in. Contrast SCRUM-225's signed-OUT link, which
could only prove ownership by mailing a confirmation to the original inbox.
An email still goes to the login's address afterwards — a receipt, so a person
whose session was taken over learns of it.

⚠️ A verified NIN is REQUIRED before a role can be added (product owner's
decision). The new account inherits that identity instead of asking again; an
account with no verified NIN has nothing to inherit and must verify first.

Realtors are out of scope for now: they sign in with a registration number
(SCRUM-207) and neither switch nor add roles here. Only buyer <-> seller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.email_verification import (
    EmailDeliveryError,
    EmailVerificationSender,
    RoleAddedEmail,
)
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.account_link import RoleAlreadyHeld
from app.services.jwt_service import JwtService, TokenPair

logger = logging.getLogger(__name__)

# The roles that can share a login and be switched between.
SWITCHABLE_ROLES = frozenset({"buyer", "seller"})
# Where a sign-in lands when the person has more than one (product decision).
DEFAULT_LANDING_ROLE = "buyer"


class SharedLoginError(RuntimeError):
    pass


class RoleNotSwitchable(SharedLoginError):
    """The caller's role or the requested one is outside buyer/seller."""


class RoleNotHeld(SharedLoginError):
    """The caller's login has no account in the requested role."""


class NinVerificationRequired(SharedLoginError):
    """Adding a role needs a verified NIN for the new account to inherit."""


class CallerAccountMissing(SharedLoginError):
    """The token outlived its account (deleted or deactivated)."""


@dataclass(frozen=True)
class SessionResult:
    """The account a switch or add landed on, and its fresh tokens."""

    user_id: UUID
    role: str
    verified_status: str
    tokens: TokenPair


class SharedLoginService:
    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        audit: AuditLogRepository,
        jwt: JwtService,
        email_sender: EmailVerificationSender,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._audit = audit
        self._jwt = jwt
        self._email_sender = email_sender

    async def switch(
        self,
        *,
        caller_id: UUID,
        caller_role: str,
        target_role: str,
        refresh_token: str | None,
    ) -> SessionResult:
        """Move the session to the caller's account in `target_role`.

        Only accounts on the caller's OWN login are reachable — the group is
        resolved from the caller's row, never from anything the client sends —
        so there is no id to tamper with.
        """
        _require_switchable(caller_role, target_role)
        owner_id = await self._users.login_owner_id(caller_id)
        if owner_id is None:
            raise CallerAccountMissing()

        target = next(
            (m for m in await self._users.login_group(owner_id) if m.role == target_role),
            None,
        )
        if target is None:
            raise RoleNotHeld()

        result = await self._open_session(
            user_id=target.id, role=target.role, verified_status=target.verified_status
        )
        await self._retire(refresh_token, caller_id=caller_id)
        logger.info(
            "shared_login.switched",
            extra={
                "from_user_id": str(caller_id),
                "to_user_id": str(target.id),
                "role": target_role,
            },
        )
        return result

    async def add_role(
        self,
        *,
        caller_id: UUID,
        caller_role: str,
        target_role: str,
        refresh_token: str | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SessionResult:
        """Create the caller's account in `target_role` on their login and
        move the session into it, ready for that role's onboarding."""
        _require_switchable(caller_role, target_role)
        if target_role == caller_role:
            raise RoleAlreadyHeld()

        account = await self._users.get_account(caller_id)
        owner_id = await self._users.login_owner_id(caller_id)
        root_id = await self._users.identity_root_id(caller_id)
        if account is None or owner_id is None or root_id is None:
            raise CallerAccountMissing()

        # Both the login and the wider identity: SCRUM-225 may have left this
        # person a seller account on a separate login (one hanging off a
        # realtor root, which 0020 deliberately did not merge). A second seller
        # account is never what anyone wants.
        on_login = {m.role for m in await self._users.login_group(owner_id)}
        if target_role in on_login or target_role in await self._users.roles_held_by_identity(
            root_id
        ):
            raise RoleAlreadyHeld()

        # Read through the identity root (see UserRepository.get_account), so a
        # linked account whose root verified counts as verified.
        if not account.nin_verified:
            raise NinVerificationRequired()

        owner = await self._users.get_account(owner_id) if owner_id != caller_id else account
        login_email = owner.email if owner is not None else account.email

        new_id = await self._users.create_with_pii(
            phone=account.phone,
            role=target_role,
            email=login_email,
            # A new seller declares owner / power-of-attorney in onboarding,
            # exactly as a fresh registration does — PoA review (§8.1) is per
            # seller account and is not something to inherit.
            seller_authority_type=None,
            full_name=account.full_name,
            first_name=account.first_name,
            last_name=account.last_name,
            # Never "phone": the phone-channel index (0008) would then treat
            # this row as a second claimant of the number.
            verification_channel="email",
            linked_identity_user_id=root_id,
            shares_login_with_user_id=owner_id,
            # The NIN is verified (checked above) and inherited. Not copied
            # from the caller: `fully_verified` may rest on things that are
            # per-account, and this account has done none of them.
            verified_status="id_verified",
            location=account.location,
            address=account.address,
        )
        await self._audit.record(
            actor_id=caller_id,
            actor_role=caller_role,
            action="user.role_added",
            entity_type="user",
            entity_id=new_id,
            new_value={"role": target_role, "shares_login_with_user_id": str(owner_id)},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        result = await self._open_session(
            user_id=new_id, role=target_role, verified_status="id_verified"
        )
        await self._retire(refresh_token, caller_id=caller_id)
        await self._notify(login_email, target_role)
        logger.info(
            "shared_login.role_added",
            extra={"from_user_id": str(caller_id), "new_user_id": str(new_id), "role": target_role},
        )
        return result

    async def _open_session(
        self, *, user_id: UUID, role: str, verified_status: str
    ) -> SessionResult:
        tokens = self._jwt.issue_pair(
            user_id=user_id,
            role=role,
            linked_user_ids=await self._users.same_person_user_ids(user_id),
        )
        await self._refresh_tokens.create(
            user_id=user_id,
            token_hash=tokens.refresh_token_hash,
            expires_at=tokens.refresh_expires_at,
        )
        return SessionResult(
            user_id=user_id, role=role, verified_status=verified_status, tokens=tokens
        )

    async def _retire(self, refresh_token: str | None, *, caller_id: UUID) -> None:
        """Revoke the session being left, so a switch does not leave a live
        refresh token behind for every account visited. Same rule as logout:
        only a token that exists and is the caller's own; anything else is a
        silent no-op rather than an error."""
        if not refresh_token:
            return
        stored = await self._refresh_tokens.get_by_hash(self._jwt.hash_token(refresh_token))
        if stored is not None and stored.user_id == caller_id and stored.revoked_at is None:
            await self._refresh_tokens.revoke(stored.id)

    async def _notify(self, email: str | None, role: str) -> None:
        """Best effort: the account already exists and the person is in it.
        Failing the request over the receipt would strand them mid-flow for
        something a retry cannot fix, so a failure is logged, not raised."""
        if not email:
            return
        try:
            await self._email_sender.send_role_added(RoleAddedEmail(to=email, role=role))
        except EmailDeliveryError as exc:
            logger.error(
                "shared_login.role_added_email_failed",
                extra={"role": role, "error": str(exc)},
            )


async def login_scope(users: UserRepository, user_id: UUID) -> tuple[UUID, list[UUID]]:
    """(owner_id, every live account id on that login) for any account id.

    For the credential and profile paths: a password belongs to the LOGIN
    OWNER whichever account the session is in, and a change to it — or to the
    email — applies to every account the login opens. For an account that
    shares nothing this is simply (user_id, [user_id]).
    """
    owner_id = await users.login_owner_id(user_id) or user_id
    member_ids = [m.id for m in await users.login_group(owner_id)]
    if user_id not in member_ids:
        # A deactivated caller is absent from login_group; still act on itself.
        member_ids.append(user_id)
    return owner_id, member_ids


def _require_switchable(caller_role: str, target_role: str) -> None:
    if caller_role not in SWITCHABLE_ROLES or target_role not in SWITCHABLE_ROLES:
        raise RoleNotSwitchable()
