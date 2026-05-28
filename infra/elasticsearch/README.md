# Elasticsearch — Local Dev

Single-node Elasticsearch 8.13 runs in docker-compose with security disabled
for local dev. The cluster holds one index — `property_listings` — that
backs every `GET /listings/search` request and the cached `GET /listings`
feed (Redis is the cache layer; ES is the search backend, never PostgreSQL
full-text search per CLAUDE.md §4).

## Quick start

```bash
# Bring up data tier
docker compose up -d elasticsearch redis

# Apply the index mapping + ping Redis
bash infra/elasticsearch/bootstrap.sh
```

The script is **idempotent** — it skips the index create if it already
exists. To pick up mapping changes, the canonical path is reindex (see
"Re-mapping" below).

## Index: `property_listings`

Backs the listing-service's search API. Source of truth is PostgreSQL
(`property_listings` partitioned table); listing-service syncs to ES via a
Celery task on every create/update.

### Field map

| Field | ES type | Why |
|---|---|---|
| `id`, `seller_id` | `keyword` | UUIDs — exact lookup only |
| `title` | `text` (maiplot_text) + `.raw` keyword | full-text + exact sort/agg |
| `description` | `text` (maiplot_text) | full-text only |
| `address_text` | `text` (maiplot_text) + `.raw` keyword | full-text + exact match |
| `property_type` | `keyword` | filter (`land\|residential\|commercial`) |
| `sale_type` | `keyword` | filter (`distress\|normal`) |
| `urgency_tag` | `keyword` | filter (`7_days\|14_days\|30_days`) |
| `status` | `keyword` | filter (`active`, `under_offer`, etc.) |
| `doc_verification_status` | `keyword` | filter (`verified`, `pending`, etc.) |
| `lga`, `state` | `keyword` | filter — Nigerian admin units |
| `asking_price_kobo` | `long` | range filter |
| `size_sqm` | `float` | range filter |
| `view_count`, `interest_count` | `integer` | sort + range |
| `location` | `geo_point` | geo_distance / bounding-box queries |
| `created_at`, `updated_at`, `expires_at`, `es_indexed_at` | `date` | sort + range |

`rejection_reason` and `deleted_at` are deliberately not indexed —
PostgreSQL is the source of truth for both, and soft-deleted rows are
filtered out before being indexed.

### Analyzer: `maiplot_text`

```
standard tokenizer + lowercase + asciifolding
```

- Standard tokenizer handles the Latin script Nigerian listings use.
- Lowercase makes searches case-insensitive ("Lekki" matches "lekki").
- Asciifolding normalizes diacritics in Yoruba/Igbo/Hausa names (e.g.
  "Ọmọ" → "Omo") so users can search without the diacritics.

Custom analyzers (edge_ngram for autocomplete, phonetic for fuzzy match)
are deferred — premature for an empty index. File a follow-up when the
search UX needs them.

### Settings

```
number_of_shards:   1
number_of_replicas: 0
```

Single-node dev only. Production overrides via an ILM index template that
sets shard count by data volume (target ~30 GB / shard) and replica count
by cluster size.

## Re-mapping

Elasticsearch does **not** allow most mapping changes in place. To pick up
schema changes:

1. Create a new index `property_listings_v2` with the new mapping.
2. Reindex: `POST _reindex { "source": {"index": "property_listings"}, "dest": {"index": "property_listings_v2"} }`
3. Swap the alias atomically (when we introduce one).

For SCRUM-39 we ship a straight `property_listings` index (no alias) —
fine while there's nothing to migrate. When the first remap is needed,
introduce the `property_listings` alias pointing at `property_listings_v2`
and switch the bootstrap script over.

## Redis

Runs at `redis:6379` inside the compose network and `localhost:${REDIS_HOST_PORT:-6379}`
on the host. Configured with `--appendonly yes` (AOF persistence) so dev
data survives container restarts.

Cache key patterns are documented in `docs/CLAUDE.md` §6. Production
moves to ElastiCache (cluster mode, 3 shards) per the stack table — no
local change required.

## Troubleshooting

- **`bootstrap.sh` says PING failed:** is `maiplot-redis` healthy?
  `docker compose ps redis`.
- **ES create returns `mapper_parsing_exception`:** the JSON mapping has
  a typo. `python -m json.tool infra/elasticsearch/mappings/property_listings.json`
  to validate first.
- **"resource_already_exists_exception":** safe — the script's idempotency
  check should catch this; if you see it from a manual `curl PUT`, the
  index is already created.
