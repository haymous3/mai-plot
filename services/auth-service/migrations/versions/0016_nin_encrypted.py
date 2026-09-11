"""recoverable NIN — encrypted value, last-4, and verified-at

Revision ID: 0016_nin_encrypted
Revises: 0015_realtor_reg_numbers
Create Date: 2026-09-11

SCRUM-224 — the admin console can now read, set, replace and clear a user's
NIN. Until this ticket the NIN was stored ONLY as one-way derivations
(`nin_hash` bcrypt for verification, `nin_lookup` HMAC for dedup), which made
"show me this user's NIN" impossible by construction. That was the original
§4 rule, and the product owner has accepted the deviation: support calls,
regulator and bank-partner requests, and correcting a mistyped registration
all need the number itself.

Three additive columns on `user_pii`
------------------------------------
  * `nin_encrypted` BYTEA — the NIN under AES-256-GCM (services/nin_crypto.py:
    version byte + nonce + ciphertext, user_id bound as associated data). Only
    an admin reveal, which is audited with a mandatory reason, ever decrypts it.
  * `nin_last4` VARCHAR(4) — the trailing four digits, so the console can show
    `•••••••1234` without a decrypt, and so an audit row can name WHICH NIN was
    set or cleared without carrying the whole number.
  * `nin_verified_at` TIMESTAMPTZ — when the registry confirmed it. There was
    no record of that before; `updated_at` on the row moves for every profile
    edit.

`nin_hash` and `nin_lookup` are unchanged. Dedup still runs on the HMAC and
the unique index still enforces one-NIN-one-account.

⚠️ No backfill, and none is possible
-------------------------------------
Every NIN verified before this migration exists only as a bcrypt hash and
cannot be recovered. Those rows keep `nin_verified = true` and get
`nin_encrypted = NULL`; the API reports them as `recoverable: false` and the
admin's remedy is Replace, which re-verifies the number with the registry.

Safety
------
Additive nullable columns on `user_pii`, which is not one of the CLAUDE.md
§11 stop-and-ask tables — but the CHANGE (NIN becomes recoverable) is a §11
item in its own right and was approved before this file was written.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_nin_encrypted"
down_revision: str | None = "0015_realtor_reg_numbers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_pii ADD COLUMN nin_encrypted BYTEA")
    op.execute("ALTER TABLE user_pii ADD COLUMN nin_last4 VARCHAR(4)")
    op.execute("ALTER TABLE user_pii ADD COLUMN nin_verified_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE user_pii DROP COLUMN nin_verified_at")
    op.execute("ALTER TABLE user_pii DROP COLUMN nin_last4")
    op.execute("ALTER TABLE user_pii DROP COLUMN nin_encrypted")
