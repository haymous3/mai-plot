"""Notification categories for the inbox tabs (SCRUM-194).

The design groups a user's notifications under a handful of tabs. Rather than
add a `category` column, the grouping is DERIVED from the `type` already stored
on every row:

  * no migration, and no backfill of the rows that already exist
  * producers keep their stable `type` contract and need no change
  * a grouping is a presentation decision, and presentation decisions that get
    written into the database are the ones you cannot revise later

The cost is that this table has to be kept in step with the producers. That is
cheap because `type` is a small, closed vocabulary set in one notifier per
service, and `_DEFAULT_CATEGORY` means a type nobody mapped still surfaces
somewhere visible rather than vanishing from every tab.
"""

from __future__ import annotations

from typing import Final

# The tab a caller can ask for. "all" is the absence of a filter, not a value
# stored anywhere.
Category = str

DEPOSITS: Final = "deposits"
BIDS: Final = "bids"
DOCUMENTS: Final = "documents"
SYSTEM: Final = "system"

CATEGORIES: Final[tuple[str, ...]] = (DEPOSITS, BIDS, DOCUMENTS, SYSTEM)

# Anything unmapped lands here. A new notification type shipped by another
# service still appears under All and under System, instead of being invisible
# in every tab — the failure mode that would actually lose a user's message.
_DEFAULT_CATEGORY: Final = SYSTEM

# ⚠️ "Bids" is the DESIGN's word. This product has no bids — it has OFFERS
# (transaction-service, §8 rule 4). The tab keeps the design's label; the data
# behind it is offers. Renaming either one is a product decision, not a
# mechanical one, so the divergence is recorded here rather than hidden.
_TYPE_TO_CATEGORY: Final[dict[str, str]] = {
    # --- offers ("Bids" in the design) -------------------------------------
    "offer_received": BIDS,
    "offer_accepted": BIDS,
    # --- documents ---------------------------------------------------------
    "document_verified": DOCUMENTS,
    "document_rejected": DOCUMENTS,
    "poa_verified": DOCUMENTS,
    "poa_rejected": DOCUMENTS,
    # --- money movement ("Deposits") ---------------------------------------
    # ⚠️ NOTHING CURRENTLY EMITS THESE. `buyer_deposit` is a payment_event
    # type, not a notification type: the deposit flow and its Paystack webhook
    # raise no notification at all, so the Deposits tab is empty until a
    # producer exists. Mapped ahead of that on purpose — the moment
    # transaction-service dispatches one of these it lands in the right tab
    # with no change here. See the SCRUM-194 plan entry.
    "deposit_received": DEPOSITS,
    "deposit_confirmed": DEPOSITS,
    "loan_disbursed": DEPOSITS,
    "title_released": DEPOSITS,
    # --- everything else is System -----------------------------------------
    # Listed explicitly rather than left to the default, so that a type
    # disappearing from a producer shows up as a stale entry here instead of
    # silently falling through.
    "listing_approved": SYSTEM,
    "listing_rejected": SYSTEM,
    "listing_expiry_warning": SYSTEM,
    "loan_approved": SYSTEM,
    "loan_rejected": SYSTEM,
    "loan_account_opened": SYSTEM,
    "inspection_assigned": SYSTEM,
    "inspection_rescheduled": SYSTEM,
    "realtor_approved": SYSTEM,
    "realtor_rejected": SYSTEM,
    "realtor_suspended": SYSTEM,
}


def category_for(notification_type: str) -> str:
    """The tab a notification type belongs under."""
    return _TYPE_TO_CATEGORY.get(notification_type, _DEFAULT_CATEGORY)


def types_in(category: str) -> list[str]:
    """Every type filed under a category, for the SQL `type IN (...)` filter.

    SYSTEM is the catch-all, so filtering on it cannot be expressed as a plain
    inclusion list — an unmapped type belongs to it too. The repository handles
    that as a NOT IN over the other categories; this returns the explicit
    members either way so the caller can choose.
    """
    return sorted(t for t, c in _TYPE_TO_CATEGORY.items() if c == category)


def types_outside_system() -> list[str]:
    """Types that are definitely NOT System — the complement used to filter it.

    Keeping this derived from the one mapping means System cannot drift out of
    step with the other tabs: whatever is not claimed elsewhere is System, by
    construction rather than by a second list someone has to remember.
    """
    return sorted(t for t, c in _TYPE_TO_CATEGORY.items() if c != SYSTEM)
