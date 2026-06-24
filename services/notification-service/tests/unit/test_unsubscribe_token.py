"""Unit tests for the unsubscribe signing token (SCRUM-122)."""

from __future__ import annotations

from uuid import uuid4

from app.services.unsubscribe_token import make_unsubscribe_token, verify_unsubscribe_token

_SECRET = "a-test-secret"


def test_round_trip_verifies() -> None:
    uid = uuid4()
    token = make_unsubscribe_token(uid, secret=_SECRET)
    assert verify_unsubscribe_token(uid, token, secret=_SECRET) is True


def test_wrong_user_is_rejected() -> None:
    token = make_unsubscribe_token(uuid4(), secret=_SECRET)
    assert verify_unsubscribe_token(uuid4(), token, secret=_SECRET) is False


def test_wrong_secret_is_rejected() -> None:
    uid = uuid4()
    token = make_unsubscribe_token(uid, secret=_SECRET)
    assert verify_unsubscribe_token(uid, token, secret="other-secret") is False


def test_garbage_token_is_rejected() -> None:
    assert verify_unsubscribe_token(uuid4(), "not-a-real-token", secret=_SECRET) is False
