#!/usr/bin/env bash
# Bootstrap Elasticsearch + Redis for Maiplot dev (SCRUM-39).
#
# Idempotent: creates the property_listings index from the JSON mapping
# only if it does not already exist, so re-running is safe and a no-op
# after the first successful run. Also pings Redis to satisfy AC #1.
#
# Usage:
#   bash infra/elasticsearch/bootstrap.sh
#
# Hosts default to localhost ports from docker-compose. Override via:
#   ES_HOST=http://es.staging:9200 REDIS_HOST=redis.staging bash bootstrap.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MAPPING_FILE="$REPO_ROOT/infra/elasticsearch/mappings/property_listings.json"

ES_HOST="${ES_HOST:-http://localhost:9200}"
INDEX_NAME="${INDEX_NAME:-property_listings}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

color() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
ok()    { color '32' "[OK]   "; }
info()  { color '36' "[INFO] "; }
warn()  { color '33' "[WARN] "; }
fail()  { color '31' "[FAIL] "; }

# AC #1 — Redis PING
printf '%s Redis ping at %s:%s ... ' "$(info)" "$REDIS_HOST" "$REDIS_PORT"
if reply=$(docker exec maiplot-redis redis-cli PING 2>&1); then
    if [[ "$reply" == "PONG" ]]; then
        printf '%s\n' "$(ok)PONG"
    else
        printf '%sunexpected reply: %s\n' "$(fail)" "$reply" >&2
        exit 1
    fi
else
    printf '%scould not exec redis-cli inside maiplot-redis container\n' "$(fail)" >&2
    exit 1
fi

# AC #2-5 — Elasticsearch property_listings index with mapping
printf '%s Elasticsearch health at %s ... ' "$(info)" "$ES_HOST"
health=$(curl -sS -o /dev/null -w '%{http_code}' "$ES_HOST" || echo "000")
if [[ "$health" != "200" ]]; then
    printf '%sgot HTTP %s — is the cluster up?\n' "$(fail)" "$health" >&2
    exit 1
fi
printf '%sreachable\n' "$(ok)"

printf '%s Check existing index %s ... ' "$(info)" "$INDEX_NAME"
exists=$(curl -sS -o /dev/null -w '%{http_code}' -I "$ES_HOST/$INDEX_NAME")
if [[ "$exists" == "200" ]]; then
    printf '%salready exists, skipping create (mapping changes require a reindex)\n' "$(warn)"
else
    printf '%screating from %s\n' "$(info)" "$MAPPING_FILE"
    response=$(curl -sS -X PUT "$ES_HOST/$INDEX_NAME" \
        -H "Content-Type: application/json" \
        --data-binary "@$MAPPING_FILE")
    if echo "$response" | grep -q '"acknowledged":true'; then
        printf '%s index %s created\n' "$(ok)" "$INDEX_NAME"
    else
        printf '%screate failed: %s\n' "$(fail)" "$response" >&2
        exit 1
    fi
fi

# Confirm the mapping is in place (covers the case where the index existed
# but with a stale mapping; we still surface what's currently active).
printf '%s Verify mapping for %s ... ' "$(info)" "$INDEX_NAME"
mapping=$(curl -sS "$ES_HOST/$INDEX_NAME/_mapping")
for required in '"location":{"type":"geo_point"}' '"property_type":{"type":"keyword"}' '"title":{' '"analyzer":"maiplot_text"'; do
    if ! echo "$mapping" | grep -q "$required"; then
        printf '%smissing expected fragment: %s\n' "$(fail)" "$required" >&2
        printf 'Full mapping:\n%s\n' "$mapping" >&2
        exit 1
    fi
done
printf '%sall expected fields present (geo_point, keyword filters, maiplot_text analyzer)\n' "$(ok)"

printf '\n%sBootstrap complete.\n' "$(ok)"
