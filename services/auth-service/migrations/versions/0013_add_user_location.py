"""the account holder's own location

Revision ID: 0013_add_user_location
Revises: 0012_password_reset_purpose
Create Date: 2026-08-28

SCRUM-193 — the seller Settings design shows a "Location" field, and a seller
has nowhere to put one. The Settings Profile tab has had a Location input since
SCRUM-188, but it is gated on `role == 'buyer'` and writes
`buyer_profiles.preferred_location`, which no other role has a row in.

Why a new column rather than reusing preferred_location
-------------------------------------------------------
They answer different questions and must not be merged:

  * `buyer_profiles.preferred_location` — "where I want to BUY". A search
    preference, collected during buyer onboarding, used to bias the feed.
  * `user_pii.location`                 — "where I AM". The account holder's
    own base, which the seller design puts beside their name and phone.

A seller could plausibly live in Abuja and be selling in Lagos; collapsing the
two would make one of those unanswerable.

Why user_pii rather than a new seller_profiles table
----------------------------------------------------
It is a plain attribute of the person, not of a selling relationship, so a
whole table with one column would be ceremony. It sits on `user_pii` rather
than `users` for the same reason `avatar_s3_key` does (SCRUM-188, migration
0011): a home location is personal data, and `users` is the deliberately
cacheable table (data-model.md principle #1).

Nullable, no backfill — nobody has stated a location yet, and an empty string
would be a worse answer than "not said".

Safety
------
Additive nullable column on `user_pii`. Not one of the CLAUDE.md §11
stop-and-ask tables (users / transactions / escrow_ledger); the product owner
was told this migration was coming when the ticket was scoped.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_add_user_location"
down_revision: str | None = "0012_password_reset_purpose"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 120 chars matches buyer_profiles.preferred_location so the two free-text
    # location fields cannot disagree about what fits.
    op.execute("ALTER TABLE user_pii ADD COLUMN location VARCHAR(120)")


def downgrade() -> None:
    op.execute("ALTER TABLE user_pii DROP COLUMN location")
