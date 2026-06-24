"""Unit tests for email rendering (SCRUM-81)."""

from __future__ import annotations

from app.services.email_templates import render_email

_UNSUB = "https://maiplot.ng/notifications/unsubscribe?uid=abc"


def test_uses_title_as_subject_when_present() -> None:
    msg = render_email(
        to="a@b.com",
        type="offer_accepted",
        title="Your offer",
        body="Body.",
        unsubscribe_url=_UNSUB,
    )
    assert msg.subject == "Your offer"
    assert msg.to == "a@b.com"


def test_falls_back_to_type_subject_then_generic() -> None:
    typed = render_email(
        to="a@b.com", type="listing_approved", title=None, body="B", unsubscribe_url=_UNSUB
    )
    assert typed.subject == "Your Maiplot listing is approved"

    generic = render_email(
        to="a@b.com", type="something_unknown", title=None, body="B", unsubscribe_url=_UNSUB
    )
    assert generic.subject == "Maiplot notification"


def test_unsubscribe_link_in_both_parts() -> None:
    msg = render_email(
        to="a@b.com",
        type="loan_approved",
        title="Decision",
        body="Approved.",
        unsubscribe_url=_UNSUB,
    )
    assert _UNSUB in msg.text_body
    assert _UNSUB in msg.html_body
    assert "Unsubscribe" in msg.html_body


def test_html_escapes_body() -> None:
    msg = render_email(
        to="a@b.com",
        type="generic",
        title="<b>Hi</b>",
        body="<script>alert(1)</script>",
        unsubscribe_url=_UNSUB,
    )
    assert "<script>" not in msg.html_body
    assert "&lt;script&gt;" in msg.html_body
    # The plain-text part keeps the raw body (no HTML context to escape).
    assert "<script>alert(1)</script>" in msg.text_body
