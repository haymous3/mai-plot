"""Admin user management (SCRUM-209).

Until now no admin surface could show a USER. Every queue is a queue of things —
listings, PoA submissions, documents, realtor applications, inspection reports,
loans — so an admin could review a seller's power of attorney without being able
to look up the seller. This is the missing side: find an account, read it, fix
its profile, suspend it, or delete it.

What an admin may change, and what they may not
-----------------------------------------------
Editable: full name, location, address, and active/suspended.

NOT editable, deliberately:
  * **role** — a buyer→admin edit is a privilege-escalation path, and the admin
    console is exactly where it would be attacked. Staff accounts are provisioned
    out of band; that is the control.
  * **email and phone** — these are VERIFIED identifiers. Editing one silently
    transfers account ownership, skips the verification that established it, and
    for a realtor breaks the MH-R login their sign-in depends on (SCRUM-207).
    If support ever needs it, it wants to be a re-verification flow, not a text
    field.

Deleting
--------
Soft, always. `audit_log` has append-only triggers and an FK to `users`, so a
user who ever caused an audit row physically cannot be hard-deleted — and CBN /
AMLON require the financial trail to survive anyway. The soft delete frees the
email and phone for reuse through the partial unique indexes (migrations
0009/0010), so the person can sign up again.

It reuses the same fail-closed active-deals guard as the user's own account
deletion: an unavailable guard REFUSES rather than assuming the account is
clear, because deleting someone mid-escrow cannot be undone through the product.

Two accounts an admin may not delete here:
  * **a staff account** (admin / legal_team) — provisioned out of band, and
    removing a colleague's access is not an ordinary console action;
  * **their own** — an admin deleting themselves ends their session mid-shift and
    leaves the queue without its operator.

Every read of one account, and every write, is audited. The LIST is not: it is a
browse surface, and auditing it would turn the audit log into a scroll log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.adapters.deals import DealChecker, DealCheckUnavailable
from app.adapters.document_storage import DocumentStorage
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import AdminUserDetail, AdminUserRow, UserRepository
from app.security import CurrentUser

logger = logging.getLogger(__name__)

# Roles this console will not delete. Staff are provisioned out of band, so
# removing one is a deliberate act elsewhere, not a row action in a user list.
_UNDELETABLE_ROLES = frozenset({"admin", "legal_team"})


class AdminUserError(RuntimeError):
    pass


class UserNotFound(AdminUserError):
    pass


class NothingToUpdate(AdminUserError):
    """The request carried no editable field."""


class CannotDeleteStaff(AdminUserError):
    """Admin and legal_team accounts are provisioned out of band."""


class CannotDeleteSelf(AdminUserError):
    """An admin deleting their own account ends their own session."""


class UserHasActiveDeals(AdminUserError):
    """The account still has a deal in flight — deleting it would strand money."""


class DeleteCheckUnavailable(AdminUserError):
    """transaction-service could not be consulted. NOT the same as "no deals"."""


class AlreadyDeleted(AdminUserError):
    pass


@dataclass(frozen=True)
class UserListPage:
    items: list[AdminUserRow]
    total: int


class AdminUserService:
    def __init__(
        self,
        *,
        users: UserRepository,
        refresh_tokens: RefreshTokenRepository,
        audit: AuditLogRepository,
        deals: DealChecker,
        storage: DocumentStorage,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._audit = audit
        self._deals = deals
        self._storage = storage

    async def list_users(
        self,
        *,
        role: str | None,
        search: str | None,
        include_deleted: bool,
        page: int,
        page_size: int,
    ) -> UserListPage:
        items, total = await self._users.list_users(
            role=role,
            search=search,
            include_deleted=include_deleted,
            page=page,
            page_size=page_size,
        )
        return UserListPage(items=items, total=total)

    async def get_user(
        self,
        *,
        user_id: UUID,
        admin: CurrentUser,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserDetail:
        """One account, and an audit row saying who looked.

        The read is audited because this is the platform's PII in one place —
        the same reasoning as `document.viewed_for_review` in SCRUM-192. Reading
        about a person is an act, even when nothing changes.
        """
        detail = await self._users.get_admin_detail(user_id)
        if detail is None:
            raise UserNotFound()
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.viewed_by_admin",
            entity_type="user",
            entity_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return detail

    async def update_profile(
        self,
        *,
        user_id: UUID,
        admin: CurrentUser,
        full_name: str | None = None,
        location: str | None = None,
        set_location: bool = False,
        address: str | None = None,
        set_address: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserDetail:
        """Edit a user's profile text. The audit row carries BEFORE and AFTER —
        "an admin changed this" is useless without what it used to say."""
        if full_name is None and not set_location and not set_address:
            raise NothingToUpdate()

        before = await self._users.get_admin_detail(user_id)
        if before is None:
            raise UserNotFound()

        updated = await self._users.admin_update_profile(
            user_id,
            full_name=full_name,
            location=location,
            set_location=set_location,
            address=address,
            set_address=set_address,
        )
        if not updated:
            # No live user_pii row — the account exists but has nothing to edit.
            raise UserNotFound()

        after = await self._users.get_admin_detail(user_id)
        assert after is not None  # the row was just written
        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.updated_by_admin",
            entity_type="user",
            entity_id=user_id,
            old_value={
                "full_name": before.full_name,
                "location": before.location,
                "address": before.address,
            },
            new_value={
                "full_name": after.full_name,
                "location": after.location,
                "address": after.address,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        logger.info("admin.user.updated", extra={"user_id": str(user_id)})
        return after

    async def set_active(
        self,
        *,
        user_id: UUID,
        active: bool,
        admin: CurrentUser,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminUserDetail:
        """Suspend or reactivate. Suspension revokes every session as well as
        blocking new logins: leaving a suspended user's existing tokens working
        until they expire would make "suspended" mean "suspended in 15 minutes"."""
        target = await self._users.get_admin_detail(user_id)
        if target is None:
            raise UserNotFound()
        if target.deleted_at is not None:
            raise AlreadyDeleted()

        changed = await self._users.set_active(user_id, active=active)
        if not changed:
            raise UserNotFound()
        if not active:
            await self._refresh_tokens.revoke_all_for_user(user_id)

        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.reactivated_by_admin" if active else "user.suspended_by_admin",
            entity_type="user",
            entity_id=user_id,
            old_value={"is_active": target.is_active},
            new_value={"is_active": active, "reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        after = await self._users.get_admin_detail(user_id)
        assert after is not None
        return after

    async def delete_user(
        self,
        *,
        user_id: UUID,
        admin: CurrentUser,
        bearer_token: str,
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Soft-delete an account, guard first.

        Order matters: every refusal happens BEFORE any write, and the
        active-deals check is fail-closed — an unreachable transaction-service
        raises rather than letting the delete through on an assumption.

        The check is SUBJECT-scoped: it asks transaction-service about the
        TARGET (`/internal/users/{id}/active-deals`, added by this ticket), not
        about the admin. The existing `/transactions/active-deals` reads its
        subject from the JWT, so reusing it here would have answered "does the
        admin have deals" and let the delete through while the target's escrow
        was still in motion — a guard checking the wrong subject is worse than
        none, because it reads as protection.
        """
        target = await self._users.get_admin_detail(user_id)
        if target is None:
            raise UserNotFound()
        if target.deleted_at is not None:
            raise AlreadyDeleted()
        # SELF before STAFF, and the order is load-bearing: an admin IS staff, so
        # checking staff first made the self-branch unreachable and answered
        # "admin accounts are managed elsewhere" to someone deleting their own
        # account. A test caught it. The specific message is the useful one.
        if target.id == admin.user_id:
            raise CannotDeleteSelf()
        if target.role in _UNDELETABLE_ROLES:
            raise CannotDeleteStaff()

        try:
            if await self._deals.has_active_deals_for(user_id=user_id, bearer_token=bearer_token):
                raise UserHasActiveDeals()
        except DealCheckUnavailable as exc:
            raise DeleteCheckUnavailable() from exc

        deleted, avatar_key = await self._users.soft_delete(user_id)
        if not deleted:
            raise AlreadyDeleted()
        await self._refresh_tokens.revoke_all_for_user(user_id)

        await self._audit.record(
            actor_id=admin.user_id,
            actor_role=admin.role,
            action="user.deleted_by_admin",
            entity_type="user",
            entity_id=user_id,
            old_value={"role": target.role, "email": target.email},
            new_value={"deleted": True, "reason": reason},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Best-effort, and last: the account is already gone as far as the
        # product is concerned, so a storage hiccup must not fail the delete or
        # leave the caller thinking it did not happen.
        if avatar_key:
            try:
                await self._storage.delete(avatar_key)
            except Exception as exc:  # noqa: BLE001 — never fail a committed delete
                logger.warning(
                    "admin.user.avatar_purge_failed",
                    extra={"user_id": str(user_id), "error": str(exc)},
                )
        logger.info("admin.user.deleted", extra={"user_id": str(user_id)})
