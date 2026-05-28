# Maiplot

Nigeria's distressed real estate marketplace — application monorepo.

This repository holds the application code (FastAPI microservices, Next.js web app, infrastructure). Project documentation, plans, and the architecture-review checklist live at the workspace root, one level up (`../CLAUDE.md`, `../plan.md`, `../review.md`, `../workflow.md`, `../data-model.md`, `../api-contracts.md`). Developer tooling lives in the separate `mai-house` repo.

## Repository layout

```
maiplot/
├── services/                     FastAPI microservices, one folder per domain
│   ├── auth-service/             registration, OTP, JWT, BVN/NIN
│   ├── listing-service/          property CRUD, media, Elasticsearch indexing
│   ├── document-service/         OCR, verification, watermarking, S3
│   ├── transaction-service/      state machine, escrow ledger, audit
│   ├── loan-service/             bank partner adapters, loan workflow
│   ├── notification-service/     Web Push, SMS (Termii), Email (SES)
│   ├── realtor-service/          onboarding, assignments, commission
│   └── analytics-service/        KPIs, admin reports (read replica)
├── frontend/
│   └── web/                      Next.js 14 — all user-facing flows
├── infra/
│   ├── kong/                     API gateway declarative config
│   ├── docker/                   Dockerfile and init scripts for shared infra
│   ├── grafana/, loki/, prometheus/   observability stack configs
│   └── terraform/                AWS infrastructure as code
├── docs/                         pointers to workspace root docs
├── docker-compose.yml            local dev stack — boots everything
├── .env.example                  shared environment variable template
└── .gitignore
```

## Quickstart (local dev)

```bash
cp .env.example .env             # fill in local values; never commit .env
docker compose up -d             # boots: postgres, redis, elasticsearch,
                                 # kong, grafana, loki, prometheus,
                                 # all FastAPI services, web app
docker compose ps                # all containers should be healthy
```

| Surface         | URL                       |
| --------------- | ------------------------- |
| Web app         | http://localhost:3000     |
| Kong proxy      | http://localhost:8000     |
| Kong admin      | http://localhost:8001     |
| Grafana         | http://localhost:3001     |
| Prometheus      | http://localhost:9090     |
| Loki            | http://localhost:3100     |
| PostgreSQL      | localhost:5432            |
| Redis           | localhost:6379            |
| Elasticsearch   | http://localhost:9200     |

## Conventions

- Read `../CLAUDE.md` at the start of any work session.
- Branch naming: `feature/SCRUM-XXX-short-description`.
- Commit format: `feat(SCRUM-XXX): description`, `fix(SCRUM-XXX): …`, etc.
- All amounts in money flows are stored as `BIGINT` kobo. Never floats.
- Every Redis read uses `get_with_fallback()`. Never raw `redis.get()`.
- Real secrets live in `.env` files (git-ignored). Only `.env.example` placeholders are committed.

See `../workflow.md` for the full development workflow.
