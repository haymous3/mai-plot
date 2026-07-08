# Kong API Gateway — Local Dev

Kong runs in **DB-less** mode against the declarative config at `kong.yml`. The
gateway listens on `:8000` (public proxy) and `:8001` (admin API). All
production traffic in front of Maiplot's FastAPI services flows through this
gateway; the per-service host ports `8011-8018` exposed by docker-compose are
for local debugging only.

## Quick start

```bash
# from maiplot/
docker compose up -d kong
docker compose up -d auth-service listing-service transaction-service \
  loan-service notification-service realtor-service document-service \
  analytics-service

# Sanity check a public route through Kong
curl -sS http://localhost:8000/auth/health
# (auth-service stub currently only exposes /health — replace with /auth/register
# once SCRUM-43 lands.)

# Verify rate limiting fires at 11+ req/min on /auth/*
./smoke.sh
```

## Route map

| Path prefix              | Upstream             | Auth                        | Rate limit |
| ------------------------ | -------------------- | --------------------------- | ---------- |
| `/auth/register`         | auth-service         | public                      | 10/min     |
| `/auth/login`            | auth-service         | public                      | 10/min     |
| `/auth/otp/*`            | auth-service         | public (token in body)      | 10/min     |
| `/auth/logout`           | auth-service         | JWT                         | 60/min     |
| `/auth/token/refresh`    | auth-service         | JWT                         | 60/min     |
| `/auth/verify/*`         | auth-service         | JWT                         | 60/min     |
| `/auth/seller/*`         | auth-service         | JWT                         | 60/min     |
| `GET /listings/*`        | listing-service      | public                      | 100/min    |
| `POST PATCH DELETE /listings/*` | listing-service | JWT                       | 30/min     |
| `/transactions/*`        | transaction-service  | JWT                         | 60/min     |
| `/loans/*`               | loan-service         | JWT (3/day enforced in svc) | 30/min     |
| `/notifications/*`       | notification-service | JWT                         | 100/min    |
| `/realtors/*`            | realtor-service      | JWT                         | 60/min     |
| `/inspections/*`         | realtor-service      | JWT                         | 60/min     |
| `/admin/listings/*`      | listing-service      | **JWT + IP whitelist**      | 60/min     |
| `/admin/poa/*`           | document-service     | **JWT + IP whitelist**      | 60/min     |
| `/admin/transactions`    | transaction-service  | **JWT + IP whitelist**      | 60/min     |
| `/admin/escrow/*`        | transaction-service  | **JWT + IP whitelist**      | 60/min     |
| `/admin/analytics`       | analytics-service    | **JWT + IP whitelist**      | 60/min     |
| `/webhooks/bank/*`       | loan-service         | HMAC (service-level)        | 200/min    |
| `/webhooks/paystack/*`   | transaction-service  | HMAC (service-level)        | 200/min    |

## JWT validation (dev stub)

The `jwt` plugin is configured with a single consumer (`maiplot-platform`)
holding an HS256 credential. The dev secret is the placeholder shipped in
`.env.example` (`change-me-to-a-long-random-string`) and is hardcoded in
`kong.yml` — Kong 3.7's env-vault expansion does not resolve at JWT-credential
load time, so referencing `{vault://env/jwt-secret}` leaves the literal
string as the validation key and every token fails with `Invalid signature`.
Production deploys replace the entire `kong.yml` via deploy-time templating
against AWS Secrets Manager; no real secret ever lives in this repo.

For local testing you can mint a token with:

```bash
# requires: pip install pyjwt  (or any JWT lib)
python -c "
import jwt, time
print(jwt.encode(
    {'iss': 'maiplot-platform', 'sub': 'dev-user', 'exp': int(time.time())+3600},
    'change-me-to-a-long-random-string', algorithm='HS256'))
"

# then
curl -sS http://localhost:8000/listings -X POST \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{}'
```

The plugin verifies signature + `exp` only — role/RBAC checks live in each
service (`SlowAPI` middleware in the FastAPI handlers). When auth-service
starts issuing real tokens (SCRUM-43), it signs with the same `JWT_SECRET`
and sets `iss=maiplot-platform`.

In production, the secret is rotated via AWS Secrets Manager and the
declarative config is templated at deploy time; nothing in this repo holds
a real secret.

## IP whitelist on `/admin/*`

The `ip-restriction` plugin allows:

```
127.0.0.1
172.16.0.0/12    # covers default Docker bridge ranges
192.168.0.0/16
10.0.0.0/8
```

For local testing, requests originating from your host (via the published
Kong port `8000`) appear to Kong as coming from the Docker bridge gateway IP,
which falls inside `172.16.0.0/12`. Requests from outside the Docker
networks (e.g., a public internet origin) get `403 Forbidden`.

In production these CIDRs are replaced with the office VPN + bastion ranges.
That swap is part of the deploy templating, not this file.

## Adding a new route

1. Pick the right upstream service block in `kong.yml`.
2. Append a route under its `routes:` list with a unique `name`.
3. Set `strip_path: false` (we keep service-owned path prefixes).
4. Attach the right rate-limit tier (see the table above).
5. Attach `jwt` for protected routes, `ip-restriction` for admin routes.
6. Reload: `docker compose restart kong` (DB-less re-reads the file on boot).
7. Add an entry to `smoke.sh` so the new route is exercised.

## Why `strip_path: false`?

Each FastAPI service owns its own path prefix (`APIRouter(prefix="/auth")`,
etc.). Kong forwards the request URL unchanged, so `/auth/register` arriving
at Kong is delivered as `/auth/register` to auth-service. If a service ever
moves to unprefixed internal routes, flip `strip_path: true` on its route(s)
locally — the gateway plays no role in path rewriting beyond that.

## Rate-limit policy backend

Currently `policy: local` — counts live in each Kong node's memory. When
SCRUM-39 brings up the Redis cluster and the deployment scales past one
Kong node, change every `policy: local` to `policy: redis` and add the Redis
connection block to each plugin config (one-line per route).
