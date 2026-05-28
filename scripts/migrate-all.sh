#!/usr/bin/env bash
# Run every service's Alembic migrations in dependency order.
#
# Each service owns its own alembic_version_<svc> table inside the shared
# `maiplot` database, so all eight histories can coexist without colliding.
# The order below is enforced because cross-service foreign keys mean
# downstream services must wait for upstream tables to exist. Specifically:
#   - realtors and loans declare bare-UUID transaction_id columns up front;
#     transaction-service's first migration is the one that adds the actual
#     FOREIGN KEY constraints back onto inspections and loans, so it MUST
#     run after both of them.
#
# Usage:
#   scripts/migrate-all.sh
#
# DATABASE_URL defaults to the local docker compose Postgres. Override for
# staging/prod by exporting it before invoking the script.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load .env so a host-side run picks up POSTGRES_HOST_PORT (often remapped
# when port 5432 is in use by another local Postgres). We then rebuild
# DATABASE_URL from those parts because the .env DATABASE_URL points at the
# `postgres` Docker network hostname, which only resolves inside the compose
# network — useless for a host-side alembic run.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-maiplot}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-change-me-local}"
POSTGRES_DB="${POSTGRES_DB:-maiplot}"
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:${POSTGRES_HOST_PORT}/${POSTGRES_DB}?ssl=disable"

SERVICES=(
    auth-service
    realtor-service
    listing-service
    document-service
    loan-service
    transaction-service
    notification-service
    analytics-service
)

for svc in "${SERVICES[@]}"; do
    printf '\n==> Migrating %s\n' "$svc"
    (
        cd "services/$svc"
        # Invoke via `python -m alembic` rather than the alembic shim so
        # Windows App Control doesn't block the spawned alembic.exe.
        uv run python -m alembic upgrade head
    )
done

printf '\nAll migrations complete.\n'
