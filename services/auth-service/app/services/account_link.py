"""Deciding whether a registration is a SECOND account for an existing person.

One person may legitimately hold more than one account — a seller who is also
a realtor. `idx_user_pii_nin_lookup` is UNIQUE, so the NIN can only live on one
of them; the others carry `users.linked_identity_user_id` pointing at that one
(the "root") and inherit its verified identity.

⚠️ THE NIN IS NOT A CREDENTIAL. A Nigerian NIN is on documents handed to banks,
agents and landlords, and a name is on every listing — so "knows the NIN and
the name" must NOT be enough to obtain an account that the platform believes is
a verified person. The security property here is entirely in WHERE THE
CONFIRMATION LINK IS SENT: the address on the EXISTING account, never the one
being typed into the form. Whoever is signing up has to be able to open the
original mailbox. Moving that send to the new address would silently turn this
into an impersonation path, so it is asserted by a test.

⚠️ Known, accepted leak: an attacker who already knows a NIN and the matching
name can tell a match from a miss by whether an email arrives at their own
address. Closing that entirely would mean emailing the new address, which is
the thing that makes this safe. The API response itself is identical either way
so the endpoint cannot be used to enumerate NINs directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.repositories.user_repo import UserRepository
from app.services.nin import InvalidNinError, lookup_nin, split_full_name, validate_nin_format

logger = logging.getLogger(__name__)


class AccountLinkError(RuntimeError):
    pass


class RoleAlreadyHeld(AccountLinkError):
    """This person already has an account in the requested role. The feature
    exists so one person can be a seller AND a realtor, not so they can hold
    two seller accounts."""


@dataclass(frozen=True)
class LinkDecision:
    """What registration should do with a claimed existing account.

    `root_user_id` is None when nothing matched — registration then proceeds as
    an ordinary new signup rather than failing, so a mistyped NIN does not dead
    end the funnel.

    `notify_email` is the address the confirmation link must go to. It is the
    ROOT's address whenever there is a match, and that is the whole point.
    """

    root_user_id: UUID | None
    notify_email: str | None

    @property
    def is_link(self) -> bool:
        return self.root_user_id is not None


class AccountLinkService:
    def __init__(self, *, users: UserRepository, pepper: str) -> None:
        self._users = users
        self._pepper = pepper

    async def decide(
        self,
        *,
        nin: str,
        claimed_full_name: str | None,
        requested_role: str,
    ) -> LinkDecision:
        """Resolve a claimed existing account to a root, or to "no match".

        Raises RoleAlreadyHeld when the person already holds the role. Every
        other failure — bad format, unknown NIN, name mismatch — is reported as
        "no match" rather than an error, because distinguishing them to the
        caller is exactly the enumeration oracle we are avoiding.
        """
        try:
            validate_nin_format(nin)
        except InvalidNinError:
            return _NO_MATCH

        match = await self._users.find_identity_by_nin_lookup(lookup_nin(nin, pepper=self._pepper))
        if match is None:
            logger.info("account_link.no_match", extra={"reason": "nin_unknown"})
            return _NO_MATCH

        if not self._names_agree(match.full_name, claimed_full_name):
            # Knowing the NIN is not enough; the name has to agree with the one
            # already on file. Logged WITHOUT either name — both are PII.
            logger.info(
                "account_link.no_match",
                extra={"reason": "name_mismatch", "root_user_id": str(match.user_id)},
            )
            return _NO_MATCH

        # The root is where the NIN lives, so siblings of a sibling still
        # resolve to the same row and a chain can never form.
        root_id = await self._users.identity_root_id(match.user_id) or match.user_id
        held = await self._users.roles_held_by_identity(root_id)
        if requested_role in held:
            raise RoleAlreadyHeld()

        logger.info(
            "account_link.matched",
            extra={"root_user_id": str(root_id), "requested_role": requested_role},
        )
        return LinkDecision(root_user_id=root_id, notify_email=match.email)

    @staticmethod
    def _names_agree(stored_full_name: str, claimed_full_name: str | None) -> bool:
        """Compare on first and last token, the same shape the registry match
        uses (SCRUM-218), so a middle name present in one and not the other
        does not fail the comparison.

        A root with no name on file cannot be matched against — there is
        nothing to check, and accepting on an empty string would mean the NIN
        alone was sufficient.
        """
        stored_first, stored_last = split_full_name(stored_full_name)
        claimed_first, claimed_last = split_full_name(claimed_full_name or "")
        if not stored_first or not claimed_first:
            return False
        if stored_first.casefold() != claimed_first.casefold():
            return False
        # A single-token name on either side matches on the first token alone;
        # requiring a surname the account never recorded would lock the real
        # owner out of their own second account.
        if stored_last and claimed_last:
            return stored_last.casefold() == claimed_last.casefold()
        return True


_NO_MATCH = LinkDecision(root_user_id=None, notify_email=None)
