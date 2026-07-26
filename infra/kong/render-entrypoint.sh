#!/usr/bin/env sh
# Kong entrypoint for the Render deployment.
#
# kong.yml is committed with local-development values — the dev JWT secret and
# docker-compose upstream hostnames. Neither works on Render, so this script
# rewrites both in place before Kong loads the file.
#
# 1. JWT consumer secret. Kong 3.7 does not expand {vault://env/...} inside a
#    JWT credential's `secret` field when loading declarative config, so the
#    signature check fails with "Invalid signature" on every request. Rewriting
#    the file first is the workaround, and it keeps the real secret out of both
#    the repo and the built image.
#
# 2. Upstream addresses. Render addresses a private service by its SLUG, which
#    carries a random suffix assigned at creation — `auth-service` is really
#    something like `auth-service-i0rz`. The compose hostnames do not resolve,
#    so every proxied route would 502. render.yaml injects the real address of
#    each service via `fromService: { property: hostport }`, so these follow the
#    services even if one is recreated with a new suffix.
#
# Every substitution is mandatory. A missing value aborts the boot rather than
# starting a gateway that silently rejects or misroutes traffic.

set -eu

CONFIG='/etc/kong/kong.yml'
JWT_PLACEHOLDER='change-me-to-a-long-random-string'

die() {
  echo "FATAL: $1" >&2
  shift
  for line in "$@"; do echo "       $line" >&2; done
  exit 1
}

# Rewrite CONFIG through a temp file so a failed substitution can never leave a
# half-written config in place. `|` as the sed delimiter avoids clashing with
# base64 secrets containing `/` or `+`.
rewrite() {
  _tmp="$(mktemp)"
  sed "$1" "$CONFIG" > "$_tmp"
  cat "$_tmp" > "$CONFIG"
  rm -f "$_tmp"
}

# --- 1. JWT consumer secret -------------------------------------------------

[ -n "${KONG_JWT_SECRET:-}" ] || die \
  "KONG_JWT_SECRET is not set." \
  "Kong would validate tokens against the dev placeholder and reject" \
  "every authenticated request. Set it to the same value as the" \
  "services' JWT_SECRET (Env Groups -> maiplot-shared -> JWT_SECRET)."

grep -q "$JWT_PLACEHOLDER" "$CONFIG" || die \
  "JWT placeholder not found in $CONFIG." \
  "kong.yml changed and this entrypoint would leave the secret unsubstituted."

rewrite "s|${JWT_PLACEHOLDER}|${KONG_JWT_SECRET}|g"

! grep -q "$JWT_PLACEHOLDER" "$CONFIG" || die "JWT substitution did not take effect."

echo "kong.yml: JWT consumer secret substituted"

# --- 2. Upstream addresses --------------------------------------------------

# Addresses we actually substituted, used by the completeness check below.
REWRITTEN=''

rewrite_upstream() {
  _svc="$1"
  _hostport="$2"

  [ -n "$_hostport" ] || die \
    "no address for upstream '${_svc}'." \
    "render.yaml should inject it via fromService/hostport. Without it Kong" \
    "would keep the compose hostname, which does not resolve on Render."

  grep -q "http://${_svc}:8000" "$CONFIG" || die \
    "upstream 'http://${_svc}:8000' not found in $CONFIG." \
    "kong.yml's service URLs changed; this mapping needs updating."

  rewrite "s|http://${_svc}:8000|http://${_hostport}|g"
  REWRITTEN="${REWRITTEN} ${_hostport}"
  echo "kong.yml: ${_svc} -> ${_hostport}"
}

rewrite_upstream auth-service         "${AUTH_SERVICE_HOSTPORT:-}"
rewrite_upstream listing-service      "${LISTING_SERVICE_HOSTPORT:-}"
rewrite_upstream document-service     "${DOCUMENT_SERVICE_HOSTPORT:-}"
rewrite_upstream transaction-service  "${TRANSACTION_SERVICE_HOSTPORT:-}"
rewrite_upstream loan-service         "${LOAN_SERVICE_HOSTPORT:-}"
rewrite_upstream notification-service "${NOTIFICATION_SERVICE_HOSTPORT:-}"
rewrite_upstream realtor-service      "${REALTOR_SERVICE_HOSTPORT:-}"
rewrite_upstream analytics-service    "${ANALYTICS_SERVICE_HOSTPORT:-}"

# Completeness check: every upstream in the file must be one we just wrote.
# Catches a service added to kong.yml without a matching rewrite_upstream line.
#
# This compares against the addresses actually substituted rather than pattern-
# matching the hostname. A Render slug is the service name plus a short random
# suffix, and that suffix can be all letters (auth-service-i0rz), so no regex
# reliably separates "compose hostname" from "rewritten slug".
_unrewritten=''
for _u in $(sed -n 's|^ *url: http://\(.*\)$|\1|p' "$CONFIG"); do
  case " ${REWRITTEN} " in
    *" ${_u} "*) ;;
    *) _unrewritten="${_unrewritten} ${_u}" ;;
  esac
done

[ -z "$_unrewritten" ] || die \
  "kong.yml has upstream(s) that were never substituted:${_unrewritten}" \
  "They still carry docker-compose hostnames, which do not resolve on Render." \
  "Add a rewrite_upstream line here and a fromService entry in render.yaml."

exec /docker-entrypoint.sh "$@"
