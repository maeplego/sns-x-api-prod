# sns-x-api-prod

**Production-oriented fork** of the learning/product repo [`sns-x-api`](https://github.com/maeplego/sns-x-api). Do **not** patch hardening work back into the learning repo — keep that tree focused on feed/ranking education.

| | |
|---|---|
| Package | `sns-x-api-prod` `3.0.4` |
| Stack | FastAPI / PostgreSQL (pgvector) / Redis / Alembic |
| Compose ports | API `8002` · Postgres `5434` · Redis `6381` · DB `sns_x_prod` |
| Frontend CORS | `http://localhost:5175` (prod UI) |
| License | MIT — filing / x-algorithm notes: see learning [`sns-x-api/README.md`](https://github.com/maeplego/sns-x-api) |

## What this fork adds

| Phase | Contents |
|---|---|
| **0** | Secret checks, liveness/readiness, hide OpenAPI in production |
| **1** | Access + refresh tokens, `token_version`, roles, Redis rate limits, RBAC deps |
| **2** | Reports, moderation (hide/suspend/labels/role), audit events |
| **3** | Metrics, TrustedHost, CI, backups, account erasure, ops doc |
| **Ops+** | Optional Sentry · Prometheus `/metrics` · Grafana compose stack |
| **Legal** | Signup requires `accept_terms` / `accept_privacy`; templates in [`docs/legal/`](docs/legal/) |

## Legal docs (templates)

- [`docs/legal/TERMS.md`](docs/legal/TERMS.md) · [`PRIVACY.md`](docs/legal/PRIVACY.md) · [`CONTACT.md`](docs/legal/CONTACT.md)
- Version constants: `app/core/legal.py` (`TERMS_VERSION` / `PRIVACY_VERSION`) — bump when you revise the docs
- These are **templates**, not legal advice. Have counsel review before public launch

## Quick start

```bash
cp .env.example .env
# Dev (with --reload):
docker compose up --build
# Prod-like API command (no reload):
docker compose -f docker-compose.prod.yml up --build
```

API: `http://localhost:8002` · Health: `GET /health` · Ready: `GET /health/ready` · Metrics: `GET /metrics`

```bash
pip install -e ".[dev]"
pytest
```

## Observability (optional)

```bash
# API must already be on :8002
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin / admin) — dashboard **sns-x-api-prod overview**

Set `SENTRY_DSN` in `.env` to enable Sentry (disabled when empty).

## Ops

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for backup/restore and deploy checklist.
