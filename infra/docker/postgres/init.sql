-- Maiplot — Postgres bootstrap script.
-- Runs once on first container start via /docker-entrypoint-initdb.d/.
-- Schema migrations are owned by SCRUM-38 (Alembic); this file only
-- installs extensions that must be present before any migration runs.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- pgcrypto provides gen_random_uuid(), used by every table per CLAUDE.md
-- ("id UUID PRIMARY KEY DEFAULT gen_random_uuid()").
