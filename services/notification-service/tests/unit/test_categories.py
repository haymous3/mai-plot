"""Notification category mapping (SCRUM-194).

The grouping is derived from `type` rather than stored, so this mapping is the
only thing standing between a producer and the wrong inbox tab.
"""

from __future__ import annotations

import pytest

from app.services import categories


@pytest.mark.parametrize(
    ("notification_type", "expected"),
    [
        ("offer_received", categories.BIDS),
        ("offer_accepted", categories.BIDS),
        ("document_verified", categories.DOCUMENTS),
        ("document_rejected", categories.DOCUMENTS),
        ("poa_verified", categories.DOCUMENTS),
        ("poa_rejected", categories.DOCUMENTS),
        ("loan_disbursed", categories.DEPOSITS),
        ("title_released", categories.DEPOSITS),
        ("listing_approved", categories.SYSTEM),
        ("listing_expiry_warning", categories.SYSTEM),
        ("inspection_assigned", categories.SYSTEM),
    ],
)
def test_known_types_land_in_the_expected_tab(notification_type: str, expected: str) -> None:
    assert categories.category_for(notification_type) == expected


def test_an_unmapped_type_falls_back_to_system_rather_than_vanishing() -> None:
    """The failure that would actually lose a user's message is a notification
    belonging to NO tab. A new producer shipping an unmapped type must still be
    reachable under All and under System."""
    assert categories.category_for("something_nobody_mapped_yet") == categories.SYSTEM


def test_system_is_the_complement_of_every_other_tab() -> None:
    """`types_outside_system()` drives a NOT IN, so if it ever included a System
    type that type would disappear from its own tab."""
    outside = set(categories.types_outside_system())
    system_members = set(categories.types_in(categories.SYSTEM))

    assert outside.isdisjoint(system_members)
    for category in (categories.DEPOSITS, categories.BIDS, categories.DOCUMENTS):
        assert set(categories.types_in(category)) <= outside


def test_every_mapped_type_belongs_to_exactly_one_tab() -> None:
    seen: dict[str, str] = {}
    for category in categories.CATEGORIES:
        for t in categories.types_in(category):
            assert t not in seen, f"{t} is in both {seen.get(t)} and {category}"
            seen[t] = category


def test_there_is_no_messages_category() -> None:
    """This product has no messaging feature; the design's Messages tab was
    dropped rather than shipped as a control that could never fill."""
    assert "messages" not in categories.CATEGORIES


def test_deposit_types_are_mapped_even_though_nothing_emits_them_yet() -> None:
    """⚠️ Nothing dispatches these today — `buyer_deposit` is a payment_event
    type, not a notification type, so the Deposits tab is empty until a
    producer exists. Mapped ahead of that so the first one to be emitted lands
    in the right tab with no code change here."""
    assert categories.category_for("deposit_received") == categories.DEPOSITS
    assert categories.category_for("deposit_confirmed") == categories.DEPOSITS
