"""Soft-deleting a user releases their phone number (SCRUM-184).

These assert DATABASE behaviour, not service behaviour: the guarantee is a
trigger plus a partial unique index (migration 0009), and the point is that it
holds for ANY writer — including raw SQL, which is how deletions are actually
performed today since no soft-delete endpoint exists. Testing through the
service layer would prove something weaker.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

_PHONE = "+2348099007700"


def _make_account(engine: Engine, email: str) -> str | None:
    """Create a phone-channel account on _PHONE. Returns the id, or None if the
    phone was already reserved. One transaction, so a clash leaves nothing."""
    try:
        with engine.begin() as conn:
            uid = conn.execute(
                text("INSERT INTO users (role, email) VALUES ('buyer', :e) RETURNING id"),
                {"e": email},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO user_pii (user_id, phone, full_name, verification_channel) "
                    "VALUES (:u, :p, 'test', 'phone')"
                ),
                {"u": uid, "p": _PHONE},
            )
            return str(uid)
    except IntegrityError:
        return None


@pytest.fixture
def clean_phone(db_engine: Engine):
    def _clear() -> None:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM user_pii WHERE phone = :p"), {"p": _PHONE})
            conn.execute(text("DELETE FROM users WHERE email LIKE 'sdfp%@test.invalid'"))

    _clear()
    yield
    _clear()


def test_phone_is_reserved_while_the_account_is_live(clean_phone: None, db_engine: Engine) -> None:
    assert _make_account(db_engine, "sdfp1@test.invalid") is not None
    assert _make_account(db_engine, "sdfp2@test.invalid") is None, (
        "a second live phone-channel account claimed the same number"
    )


def test_soft_delete_mirrors_into_user_pii_and_frees_the_phone(
    clean_phone: None, db_engine: Engine
) -> None:
    first = _make_account(db_engine, "sdfp1@test.invalid")
    assert first is not None

    with db_engine.begin() as conn:
        conn.execute(text("UPDATE users SET deleted_at = NOW() WHERE id = :i"), {"i": first})

    # The trigger is what makes this work: the partial index cannot read
    # users.deleted_at, so the value has to be mirrored onto user_pii.
    with db_engine.connect() as conn:
        mirrored = conn.execute(
            text("SELECT deleted_at IS NOT NULL FROM user_pii WHERE user_id = :i"), {"i": first}
        ).scalar_one()
    assert mirrored, "trigger did not mirror deleted_at onto user_pii"

    assert _make_account(db_engine, "sdfp2@test.invalid") is not None, (
        "phone still reserved by a soft-deleted account"
    )


def test_restoring_an_account_whose_phone_was_reclaimed_is_refused(
    clean_phone: None, db_engine: Engine
) -> None:
    """Undelete must fail loudly rather than leave two live accounts sharing a
    number — which would make the OTP lookup ambiguous again."""
    first = _make_account(db_engine, "sdfp1@test.invalid")
    assert first is not None
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE users SET deleted_at = NOW() WHERE id = :i"), {"i": first})
    assert _make_account(db_engine, "sdfp2@test.invalid") is not None

    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(text("UPDATE users SET deleted_at = NULL WHERE id = :i"), {"i": first})


def test_email_channel_accounts_are_unaffected_by_the_index(
    clean_phone: None, db_engine: Engine
) -> None:
    """Email-channel rows sit outside the predicate entirely, so they neither
    reserve a phone nor are blocked by one (SCRUM-183 behaviour, re-pinned
    here because 0009 rewrote the index)."""
    assert _make_account(db_engine, "sdfp1@test.invalid") is not None
    with db_engine.begin() as conn:
        uid = conn.execute(
            text("INSERT INTO users (role, email) VALUES ('buyer', :e) RETURNING id"),
            {"e": "sdfp2@test.invalid"},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO user_pii (user_id, phone, full_name, verification_channel) "
                "VALUES (:u, :p, 'test', 'email')"
            ),
            {"u": uid, "p": _PHONE},
        )
