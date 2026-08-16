# sns-x-api-prod

**Production-oriented fork** of the learning/product repo [`sns-x-api`](../sns-x-api). Do **not** patch hardening work back into the learning repo — keep that tree focused on feed/ranking education.

| | |
|---|---|
| Package | `sns-x-api-prod` `3.0.0` |
| Stack | FastAPI / PostgreSQL (pgvector) / Redis / Alembic |
| Compose ports | API `8002` · Postgres `5434` · Redis `6381` · DB `sns_x_prod` |
| Frontend CORS | `http://localhost:5175` (prod UI) |
| License | MIT — filing / x-algorithm notes: see learning [`sns-x-api/README.md`](../sns-x-api/README.md) |

## What this fork adds

| Phase | Contents |
|---|---|
| **0** | Secret checks, liveness/readiness, hide OpenAPI in production |
| **1** | Access + refresh tokens, `token_version`, roles, Redis rate limits, RBAC deps |
| **2** | Reports, moderation (hide/suspend/labels/role), audit events |
| **3** | Metrics counters, TrustedHost, CI, backups, account erasure, ops doc |

## Quick start

```bash
cp .env.example .env
# Dev (with --reload):
docker compose up --build
# Prod-like API command (no reload):
docker compose -f docker-compose.prod.yml up --build
```

API: `http://localhost:8002` · Health: `GET /health` · Ready: `GET /health/ready`

```bash
uv sync --extra dev   # or pip install -e ".[dev]"
pytest
```

## Ops

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for backup/restore and deploy checklist.
