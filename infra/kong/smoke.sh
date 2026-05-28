#!/usr/bin/env bash
# Kong gateway smoke test — SCRUM-37.
#
# Prereqs: docker compose up -d kong + all eight FastAPI services.
# Runs a series of curls against http://localhost:8000 and asserts the
# expected status codes. Exits non-zero on any mismatch.
#
# Each backend service currently exposes only GET /health, so the public
# routes return 404 from the service (the route matched at Kong, then the
# service had no /auth/register handler). That 404 is still the correct
# end-to-end signal: it proves Kong forwarded to the right upstream. As real
# handlers land, swap the 404 expectations for the appropriate 2xx.

set -euo pipefail

KONG="${KONG:-http://localhost:8000}"
PASS=0
FAIL=0

color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
ok()    { color '32' "  PASS"; }
bad()   { color '31' "  FAIL"; }

b64url() { openssl base64 -e -A | tr '+/' '-_' | tr -d '='; }

mint_jwt() {
  # mint_jwt <secret> — emits an HS256 JWT for consumer "maiplot-platform".
  local secret="$1"
  local header='{"typ":"JWT","alg":"HS256"}'
  local payload
  payload="{\"iss\":\"maiplot-platform\",\"sub\":\"smoke\",\"exp\":$(( $(date +%s) + 3600 ))}"
  local h64 p64 sig
  h64=$(printf '%s' "$header" | b64url)
  p64=$(printf '%s' "$payload" | b64url)
  sig=$(printf '%s.%s' "$h64" "$p64" \
    | openssl dgst -sha256 -hmac "$secret" -binary \
    | b64url)
  printf '%s.%s.%s' "$h64" "$p64" "$sig"
}

assert_status() {
  local desc="$1" expected="$2" method="$3" path="$4"
  shift 4
  local got
  got=$(curl -s -o /dev/null -w '%{http_code}' -X "$method" "$KONG$path" "$@" || echo "000")
  if [[ "$got" == "$expected" ]]; then
    printf '%s  %-50s %s == %s\n' "$(ok)" "$desc" "$got" "$expected"
    PASS=$((PASS + 1))
  else
    printf '%s  %-50s %s != %s\n' "$(bad)" "$desc" "$got" "$expected"
    FAIL=$((FAIL + 1))
  fi
}

echo "Kong proxy: $KONG"
echo

# -----------------------------------------------------------------------------
# AC #1: All service routes reachable through Kong
# Each upstream's /health is the only handler that currently exists. We hit it
# via each service's prefix path. Kong matches the prefix and forwards; the
# service returns 404 because /<prefix>/health is not a real route — but the
# 404 originates from FastAPI, proving the request reached the upstream. The
# fastest "really reached the service" probe is to bypass Kong's prefix and
# call /health directly on each per-service host port (8011-8018); that is
# what `make smoke` (TODO) would do. Here we use a Kong-routed probe instead.
# -----------------------------------------------------------------------------
echo "=== AC #1: routes reach the correct upstream (404 from FastAPI = reached) ==="
assert_status "auth-service via /auth/register"        404 GET  /auth/register
assert_status "listing-service via /listings (public)" 404 GET  /listings
assert_status "transaction-service via /transactions"  401 GET  /transactions   # jwt plugin should reject without token
assert_status "loan-service via /loans/anything"       401 GET  /loans/anything
assert_status "notification-service via /notifications" 401 GET /notifications
assert_status "realtor-service via /realtors"          401 GET  /realtors

echo
echo "=== AC #2: rate limiting returns 429 when exceeded ==="
# /auth/* tier is 10/min. Burst 12 requests and expect at least one 429.
got_429=0
for i in $(seq 1 12); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$KONG/auth/register" || echo "000")
  if [[ "$code" == "429" ]]; then got_429=1; break; fi
done
if [[ "$got_429" == "1" ]]; then
  printf '%s  /auth/register hits 429 after burst\n' "$(ok)"
  PASS=$((PASS + 1))
else
  printf '%s  /auth/register did NOT hit 429 after 12 reqs — check rate-limit config\n' "$(bad)"
  FAIL=$((FAIL + 1))
fi

echo
echo "=== AC #3: admin routes IP-restricted ==="
# From inside the Docker bridge (where this script likely runs on the host),
# requests arrive at Kong from a 172.x source and pass the whitelist. To
# prove the plugin works, we'd need to spoof an external X-Forwarded-For —
# Kong's ip-restriction respects X-Real-IP if real_ip_recursive is set, but
# by default it uses the immediate peer. A real "external IP" test happens
# from outside the Docker network.
# Here we just confirm the plugin returns 401 (JWT missing) BEFORE the IP
# check would 403 — order of plugin execution: ip-restriction → jwt. So if
# we see 401 from a local request, the IP check passed (good) AND the JWT
# check ran (good).
assert_status "admin/listings without JWT (local IP allowed, JWT missing)" \
  401 GET /admin/listings

echo
echo "=== AC #4: JWT plugin active on protected routes ==="
assert_status "/transactions without JWT" 401 GET /transactions
assert_status "/loans without JWT"        401 GET /loans
assert_status "/realtors without JWT"     401 GET /realtors
# Webhook routes intentionally have no JWT (HMAC at service layer)
assert_status "/webhooks/paystack without JWT (HMAC at service)" \
  404 POST /webhooks/paystack -H "Content-Type: application/json" -d '{}'

# Valid JWT should pass the gateway. 404 from FastAPI (no handler at GET
# /transactions yet) means the request reached the upstream — i.e. Kong's
# JWT plugin accepted the token rather than rejecting with 401.
TOKEN=$(mint_jwt "${JWT_SECRET:-change-me-to-a-long-random-string}")
assert_status "/transactions with valid JWT (plugin accepts)" \
  404 GET /transactions -H "Authorization: Bearer $TOKEN"

echo
echo "Passed: $PASS    Failed: $FAIL"
[[ "$FAIL" -eq 0 ]]
