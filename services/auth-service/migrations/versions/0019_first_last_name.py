"""collect first and last name separately (SCRUM-231)

Revision ID: 0019_first_last_name
Revises: 0018_soft_delete_frees_nin

Three places MATCH a person's name against the NIN registry — NIN verification
(SCRUM-218), account linking (SCRUM-225) and the admin NIN console (SCRUM-224)
— and every one of them went through `split_full_name`, which takes the first
and last TOKENS of a single string. That is a guess: "Ada Van der Berg" splits
into first=Ada, last=Berg, and the registry says no.

Collecting the two names separately means the match sends EXACTLY what the
user typed, with no heuristic in the loop — and the form can tell them why:
these must match the NIN slip.

`full_name` is KEPT, and stays NOT NULL. It is what every greeting, table and
admin list displays, and there is no reason to touch fourteen display sites.
Registration and profile update now derive it as "First Last".

⚠️ NO BACKFILL, ON PURPOSE. Populating first/last from the existing strings
would freeze the very splitting heuristic this migration exists to remove, and
freeze it into the DATA rather than the code where it can at least be fixed.
Existing accounts keep `full_name` only; readers fall back to splitting it when
the parts are null (see `name_parts` in services/nin.py), and the person
corrects themselves in Settings. New accounts never hit the fallback.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019_first_last_name"
down_revision: str | None = "0018_soft_delete_frees_nin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: pre-existing rows have only full_name, and that is deliberate.
    # TEXT, not VARCHAR, for the same reason full_name is — Nigerian names run
    # long and a compound surname must not be truncated at an arbitrary limit.
    op.execute("ALTER TABLE user_pii ADD COLUMN first_name TEXT")
    op.execute("ALTER TABLE user_pii ADD COLUMN last_name TEXT")


def downgrade() -> None:
    # full_name was maintained alongside throughout, so nothing is lost.
    op.execute("ALTER TABLE user_pii DROP COLUMN IF EXISTS last_name")
    op.execute("ALTER TABLE user_pii DROP COLUMN IF EXISTS first_name")
