"""realtor Maihomme registration numbers — the approved realtor's login id

Revision ID: 0015_realtor_reg_numbers
Revises: 0014_add_user_address
Create Date: 2026-09-05

SCRUM-207 — a realtor no longer supplies an ESVARBON licence at onboarding.
Instead the admin verifies the application and the platform ISSUES a Maihomme
registration number, emails it to the realtor, and that number (plus their
password) is how they sign in from then on.

Why the number lives in AUTH-SERVICE and not in `realtors`
----------------------------------------------------------
It is issued during realtor approval, which realtor-service owns — but it has
to be resolvable at LOGIN, and login is auth-service's. Putting it in
`realtors` would mean auth-service reading another service's table on the
login path (CLAUDE.md §3). So auth-service owns the identifier and exposes an
internal issuance endpoint that realtor-service calls when an admin approves.

Deliberately NOT a column on `users`: that table is one of the three §11
stop-and-ask tables, and this needs no schema change there. A one-row-per-
realtor side table also keeps "has a number" a cheap EXISTS on the login path.

Uniqueness + soft delete
------------------------
Two different rules, on purpose:

  * `registration_number` is UNIQUE **unconditionally**. A number identifies a
    person; it must never be handed to somebody else, even after a revocation.
  * `user_id` is unique only WHERE deleted_at IS NULL, so a revoked row can be
    superseded by a freshly issued one for the same realtor.

Every read path filters `deleted_at IS NULL` — a revoked number must stop
authenticating the moment it is revoked. Nothing revokes one today; the shape
is here so that adding it later is not a migration.

Format
------
`MH-R-000123`, from a dedicated sequence. Sequence-backed rather than random
so issuance can never collide and never needs a retry loop, and short enough
to be read down a phone line to a realtor who cannot find the email. The
prefix is duplicated in app/services/registration_number.py (a test asserts
the two agree — see tests/integration/test_realtor_registration_number.py).

Backfill
--------
Realtors approved BEFORE this ships have no number, and after SCRUM-207 an
approved realtor cannot sign in with their email — so without a backfill every
existing approved realtor is locked out. They get numbers here.

⚠️ The backfill is GUARDED by an information_schema check, because `realtors`
belongs to realtor-service and auth-service's migrations can (and on a fresh
database do) run first. On a fresh DB the guard finds no table, inserts
nothing, and there is nothing to insert — the realtors table cannot hold rows
that predate its own creation.

Numbering order among backfilled realtors is best-effort (oldest approval
first): `nextval` evaluation order against an ordered subquery is not a
promise Postgres makes, and nothing depends on it.

Safety: new table + new sequence only. No §11 table is touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_realtor_reg_numbers"
down_revision: str | None = "0014_add_user_address"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE realtor_registration_number_seq START WITH 1 INCREMENT BY 1")
    op.execute(
        """
        CREATE TABLE realtor_registration_numbers (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID NOT NULL REFERENCES users(id),
            registration_number VARCHAR(32) NOT NULL UNIQUE,
            issued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            deleted_at          TIMESTAMPTZ
        )
        """
    )
    # One LIVE number per realtor. Partial so a revoked row can be superseded.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_realtor_registration_numbers_user
            ON realtor_registration_numbers (user_id)
            WHERE deleted_at IS NULL
        """
    )

    # Backfill already-approved realtors. Guarded: `realtors` is owned by
    # realtor-service and may not exist yet.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'realtors'
            ) THEN
                INSERT INTO realtor_registration_numbers (user_id, registration_number)
                SELECT s.id,
                       'MH-R-' || LPAD(nextval('realtor_registration_number_seq')::text, 6, '0')
                FROM (
                    SELECT r.id
                    FROM realtors r
                    JOIN users u ON u.id = r.id
                    WHERE r.approval_status = 'approved'
                      AND u.deleted_at IS NULL
                      AND u.is_active
                    ORDER BY COALESCE(r.approved_at, r.created_at)
                ) s;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE realtor_registration_numbers")
    op.execute("DROP SEQUENCE realtor_registration_number_seq")
