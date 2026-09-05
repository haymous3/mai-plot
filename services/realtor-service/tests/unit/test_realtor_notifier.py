"""Realtor decision message bodies (SCRUM-71, extended by SCRUM-207).

The approval message is the realtor's ONLY copy of the registration number they
sign in with, so what it says is behaviour, not presentation.
"""

from __future__ import annotations

from app.services.realtor_notifier import _decision_message


def test_approved_message_states_the_number_and_what_to_do_with_it() -> None:
    type_, title, body = _decision_message(
        status="approved", reason=None, registration_number="MH-R-000123"
    )

    assert type_ == "realtor_approved"
    assert "approved" in title.lower()
    assert "MH-R-000123" in body
    # Not just the number — a realtor who does not know it is now their login id
    # has no reason to try it in the sign-in field.
    assert "sign in" in body.lower()


def test_approved_without_a_number_points_at_support_not_at_none() -> None:
    """Unreachable through RealtorReviewService, which always issues first. The
    fallback exists so a future caller cannot email the word "None" to a realtor
    as their credential."""
    _, _, body = _decision_message(status="approved", reason=None, registration_number=None)

    assert "None" not in body
    assert "support" in body.lower()


def test_rejected_message_carries_the_reason_and_no_number() -> None:
    type_, _, body = _decision_message(status="rejected", reason="blurry ID")

    assert type_ == "realtor_rejected"
    assert "blurry ID" in body
    assert "MH-R-" not in body


def test_suspended_message_carries_the_reason() -> None:
    type_, _, body = _decision_message(status="suspended", reason="fraud")

    assert type_ == "realtor_suspended"
    assert "fraud" in body
