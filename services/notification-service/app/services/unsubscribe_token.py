"""Signed token for the email unsubscribe link (SCRUM-122).

The unsubscribe endpoint is unauthenticated (it's clicked from an email), so the
link carries an HMAC of the user id. Without the server secret an attacker can't
forge a token for another user, so the endpoint can't be used to opt arbitrary
users out. Verification is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
from uuid import UUID


def make_unsubscribe_token(user_id: UUID, *, secret: str) -> str:
    return hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()


def verify_unsubscribe_token(user_id: UUID, token: str, *, secret: str) -> bool:
    expected = make_unsubscribe_token(user_id, secret=secret)
    return hmac.compare_digest(expected, token)
