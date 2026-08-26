"""Soft-deleting a user releases their email address (SCRUM-185).

The counterpart to test_soft_delete_frees_phone. Like that one, these assert
DATABASE behaviour: the guarantee is a partial unique index (migration 0010),
and it must hold for any writer — including the raw SQL that deletions are
actually performed with today.

The bug being pinned is specific: before 0010 the service and the database
DISAGREED. get_active_by_email filters deleted_at, so registration's duplicate
check passed for a soft-deleted address — and then the INSERT hit the global
unique constraint, surfacing as a 500 instead of a clean 400.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

_EMAIL = "sdfe1@test.invalid"


def _make_account(engine: Engine, email: str | None) -> str | None:
    """Create a users row. Returns the id, or None if the address was taken."""
    try:
        with engine.begin() as conn:
            return str(
                conn.execute(
                    text("INSERT INTO users (role, email) VALUES ('buyer', :e) RETURNING id"),
                    {"e": email},
                ).scalar_one()
            )
    except IntegrityError:
        return None


@pytest.fixture
def clean_emails(db_engine: Engine) -> Generator[None, None, None]:
    def _clear() -> None:
        with db_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM user_pii WHERE user_id IN "
                    "(SELECT id FROM users WHERE email LIKE 'sdfe%@test.invalid')"
                )
            )
            conn.execute(text("DELETE FROM users WHERE email LIKE 'sdfe%@test.invalid'"))

    _clear()
    yield
    _clear()


def test_email_is_reserved_while_the_account_is_live(clean_emails: None, db_engine: Engine) -> None:
    assert _make_account(db_engine, _EMAIL) is not None
    assert _make_account(db_engine, _EMAIL) is None, "two live accounts shared one address"


def test_soft_delete_frees_the_email(clean_emails: None, db_engine: Engine) -> None:
    first = _make_account(db_engine, _EMAIL)
    assert first is not None
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE users SET deleted_at = NOW() WHERE id = :i"), {"i": first})

    assert _make_account(db_engine, _EMAIL) is not None, (
        "address still reserved by a soft-deleted account — this is the case that "
        "used to surface as a 500 at registration"
    )


def test_restoring_an_account_whose_email_was_reclaimed_is_refused(
    clean_emails: None, db_engine: Engine
) -> None:
    first = _make_account(db_engine, _EMAIL)
    assert first is not None
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE users SET deleted_at = NOW() WHERE id = :i"), {"i": first})
    assert _make_account(db_engine, _EMAIL) is not None

    with pytest.raises(IntegrityError):
        with db_engine.begin() as conn:
            conn.execute(text("UPDATE users SET deleted_at = NULL WHERE id = :i"), {"i": first})


def test_null_emails_may_repeat(clean_emails: None, db_engine: Engine) -> None:
    """users.email is nullable and several accounts may legitimately have none;
    a unique index must not collapse them (Postgres allows duplicate NULLs, but
    pin it so a future 'NULLS NOT DISTINCT' does not break registration)."""
    ids = [_make_account(db_engine, None), _make_account(db_engine, None)]
    try:
        assert all(ids), "a second NULL email was rejected"
    finally:
        with db_engine.begin() as conn:
            for i in ids:
                if i:
                    conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": i})
