"""profile photo: store the private-bucket key for a user's avatar

Revision ID: 0011_add_avatar_key
Revises: 0010_soft_delete_frees_email
Create Date: 2026-08-27

SCRUM-188 — the Settings design draws a profile photo with a camera badge, and
the onboarding export draws the same control. Neither could be built because
there was no column, no endpoint and no S3 path for a user photo anywhere in
auth-service.

Why `user_pii` and not `users`
------------------------------
A photograph of a person is personal data under NDPR, and `users` is the
deliberately safely-cacheable table (data-model.md design principle #1) — it
holds role, status and timestamps, while every identifying field (phone,
full_name, BVN/NIN hashes) lives on `user_pii`. An avatar belongs with the
latter group. It costs `GET /auth/me` nothing: that read already joins
`user_pii` to report `bvn_verified`/`nin_verified`.

Only the KEY is stored, never the image bytes — the same rule the PoA upload
path follows. The object sits in the PRIVATE documents bucket and is served
solely through a 15-minute pre-signed URL (CLAUDE.md §4).

Safety
------
Adding a NULLable column with no default, no backfill and no constraint cannot
fail and cannot conflict with existing rows: every current user simply has no
avatar. Nothing reads the column until the application ships alongside it, so
this is safe to apply ahead of the deploy.

512 chars is generous for the `avatar/{user_id}/{uuid}.{ext}` key shape (~60
chars); it matches the headroom the codebase already gives S3 keys elsewhere.

§11 schema change on the `users` family — approved for this ticket.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_add_avatar_key"
down_revision: str | None = "0010_soft_delete_frees_email"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_pii",
        sa.Column("avatar_s3_key", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    # Dropping the column orphans whatever objects the bucket still holds under
    # avatar/. That is deliberate: a downgrade must not issue S3 deletes, and
    # the objects are unreachable without a key anyway (private bucket, no
    # public URL). An operator rolling back should run the erasure sweep
    # separately if the data must actually go.
    op.drop_column("user_pii", "avatar_s3_key")
