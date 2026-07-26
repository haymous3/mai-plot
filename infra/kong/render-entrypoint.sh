#!/usr/bin/env sh
# Kong entrypoint for the Render deployment.
#
# Substitutes the real JWT consumer secret into kong.yml at container start.
#
# Why a startup rewrite instead of Kong's env-var indirection: Kong 3.7 does
# not expand {vault://env/...} references inside a JWT credential's `secret`
# field when loading declarative config, so the token signature check fails
# with "Invalid signature" on every request. Rewriting the file before Kong
# reads it is the workaround, and it keeps the real secret out of both the
# repo and the built image.
#
# kong.yml ships the dev placeholder (see its header); this replaces it with
# $KONG_JWT_SECRET, which must equal the JWT_SECRET every FastAPI service
# signs with.

set -eu

PLACEHOLDER='change-me-to-a-long-random-string'
CONFIG='/etc/kong/kong.yml'

if [ -z "${KONG_JWT_SECRET:-}" ]; then
  echo "FATAL: KONG_JWT_SECRET is not set. Kong would validate tokens against" >&2
  echo "       the dev placeholder and reject every authenticated request." >&2
  echo "       Set it to the same value as the services' JWT_SECRET." >&2
  exit 1
fi

if ! grep -q "$PLACEHOLDER" "$CONFIG"; then
  echo "FATAL: placeholder secret not found in $CONFIG — kong.yml changed and" >&2
  echo "       this entrypoint would leave the JWT secret unsubstituted." >&2
  exit 1
fi

# Write to a temp file first so a failed substitution can never leave a
# half-rewritten config in place. `|` as the delimiter avoids clashing with
# base64 secrets containing `/` or `+`.
TMP="$(mktemp)"
sed "s|${PLACEHOLDER}|${KONG_JWT_SECRET}|g" "$CONFIG" > "$TMP"
cat "$TMP" > "$CONFIG"
rm -f "$TMP"

if grep -q "$PLACEHOLDER" "$CONFIG"; then
  echo "FATAL: substitution did not take effect." >&2
  exit 1
fi

echo "kong.yml: JWT consumer secret substituted from KONG_JWT_SECRET"

exec /docker-entrypoint.sh "$@"
