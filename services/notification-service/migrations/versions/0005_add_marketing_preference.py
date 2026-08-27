"""marketing email preference, opt-IN by default

Revision ID: 0005_add_marketing_preference
Revises: 0004_notification_archived_at
Create Date: 2026-08-27

SCRUM-188 — the Settings design draws a fourth toggle, "Marketing Emails /
Receive promotional content and offers", alongside the three transactional
channels. There was no column behind it.

⚠️ DEFAULT FALSE deliberately breaks this table's convention
--------------------------------------------------------
Every other flag here defaults TRUE, because `notification_preferences` is an
OPT-OUT model: a missing row means "all defaults", and the repository returns
enabled-everything when no row exists. That is right for transactional
messages — a user who never touched Settings still needs their OTP, their
deal-accepted alert and their loan decision.

Marketing is not transactional. NDPR (CLAUDE.md §9) treats promotional
messaging as requiring explicit, affirmative consent, so it must default OFF
and become TRUE only when a user actually flips the switch. Defaulting TRUE
here would opt every existing account into marketing via a migration they
never saw.

The design agrees: it draws Marketing Emails OFF while Email, SMS and Push are
all ON.

This asymmetry is load-bearing. Anything that later "harmonises" these four
flags to a single default reintroduces a compliance problem, so
`NotificationPreferences` carries the same warning beside the field.

Safety
------
NOT NULL with a DEFAULT is safe here: Postgres 11+ adds such a column without
rewriting the table, and every existing row takes FALSE — the conservative
value. No backfill, no constraint that can fail.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_marketing_preference"
# NB: the revision ID is "0004_notification_archived_at" — it does NOT match
# that migration's FILENAME (0004_add_notification_archived_at.py). Alembic
# chains on the id, so using the filename here would fail to locate it.
down_revision: str | None = "0004_notification_archived_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column(
            "marketing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_preferences", "marketing_enabled")
