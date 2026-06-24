"""Email rendering for notification emails (SCRUM-81).

Turns a notification (type + title + body) into a subject + HTML + text email.
Subjects are tailored per known notification type (listing approved, loan
decision, transaction milestones, document verification) with a sensible
fallback. Every email carries an unsubscribe link (NDPR). Title/body are
HTML-escaped in the HTML part as defence in depth.
"""

from __future__ import annotations

import html

from app.adapters.ses_email import EmailMessage

# Per-type subject lines. The notification's own title wins when present; this is
# the fallback when a type has no title set.
_DEFAULT_SUBJECTS: dict[str, str] = {
    "listing_approved": "Your Maiplot listing is approved",
    "listing_rejected": "Update on your Maiplot listing",
    "loan_approved": "Your Maiplot loan decision",
    "loan_rejected": "Your Maiplot loan decision",
    "document_verified": "Your Maiplot document was verified",
    "document_rejected": "Action needed on your Maiplot document",
    "offer_accepted": "Your Maiplot offer was accepted",
    "transaction_completed": "Your Maiplot transaction is complete",
}
_GENERIC_SUBJECT = "Maiplot notification"


def _subject_for(*, type: str, title: str | None) -> str:
    if title:
        return title
    return _DEFAULT_SUBJECTS.get(type, _GENERIC_SUBJECT)


def render_email(
    *,
    to: str,
    type: str,
    title: str | None,
    body: str,
    unsubscribe_url: str,
) -> EmailMessage:
    subject = _subject_for(type=type, title=title)
    heading = title or "Maiplot"

    text_body = (
        f"{body}\n\n"
        "—\n"
        "You're receiving this because you have a Maiplot account.\n"
        f"Unsubscribe: {unsubscribe_url}\n"
    )

    html_body = (
        "<!doctype html><html><body "
        'style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;line-height:1.5;">'
        f'<h2 style="margin:0 0 12px;">{html.escape(heading)}</h2>'
        f"<p>{html.escape(body)}</p>"
        '<hr style="border:none;border-top:1px solid #e0e0e0;margin:24px 0;">'
        '<p style="font-size:12px;color:#777;">'
        "You're receiving this because you have a Maiplot account. "
        f'<a href="{html.escape(unsubscribe_url)}">Unsubscribe</a>.'
        "</p></body></html>"
    )

    return EmailMessage(to=to, subject=subject, html_body=html_body, text_body=text_body)
