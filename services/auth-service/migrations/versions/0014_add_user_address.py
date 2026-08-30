"""the account holder's postal address

Revision ID: 0014_add_user_address
Revises: 0013_add_user_location
Create Date: 2026-08-30

SCRUM-201 — onboarding now collects a full name, an address and a NIN from
every role. The first two of those had nowhere to go: registration owns the
name (SCRUM-197), but no table held an address.

Why a THIRD place-ish column, and how the three differ
------------------------------------------------------
The product owner chose to keep the address distinct rather than fold it into
`location`. So `user_pii` now carries two, and `buyer_profiles` a third, and
they answer three different questions:

  * `user_pii.address`                  — "where I live". A postal address,
                                          the KYC-style datum (AMLON §9).
  * `user_pii.location`                 — "where I am", city/state level
                                          (SCRUM-193, shown in Settings).
  * `buyer_profiles.preferred_location` — "where I want to BUY". A buyer's
                                          search preference, not about them.

⚠️ Do not "tidy" these into one. Each was added for a stated reason, and a
seller living in Abuja, based in Lagos, is not a contradiction.

Length
------
TEXT rather than a VARCHAR(n). A Nigerian street address with an estate name
and landmark directions runs long, and there is no downstream format that
depends on a ceiling — unlike `location`, which was sized to match
`preferred_location` so the two could not disagree about what fits.

Safety
------
Additive nullable column on `user_pii`. Not one of the CLAUDE.md §11
stop-and-ask tables (users / transactions / escrow_ledger). Nullable with no
backfill: every existing account predates the field and has no address to
state, and an empty string would be a worse answer than "not said".
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_add_user_address"
down_revision: str | None = "0013_add_user_location"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_pii ADD COLUMN address TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE user_pii DROP COLUMN address")
