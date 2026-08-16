# sns-x-api-prod

**Production-oriented fork** of the learning/product repo [`sns-x-api`](https://github.com/maeplego/sns-x-api). Do **not** patch hardening work back into the learning repo — keep that tree focused on feed/ranking education.

| | |
|---|---|
| Package | `sns-x-api-prod` `3.0.6` |
| Stack | FastAPI / PostgreSQL (pgvector) / Redis / Alembic |
| Compose ports | API `8002` · Postgres `5434` · Redis `6381` · DB `sns_x_prod` |
| Frontend | [`sns-x-frontend-prod`](https://github.com/maeplego/sns-x-frontend-prod) on `:5175` |
| License | MIT — filing / x-algorithm notes: see learning [`sns-x-api/README.md`](https://github.com/maeplego/sns-x-api) |

> **Portfolio note:** This stack is meant to show production *thinking* (auth, moderation, legal consent, ops, AWS design). It is **not** required to run on a public AWS account. Local Compose is the intended demo.

## What this repo demonstrates

| Theme | Where to look |
|---|---|
| Learning vs product split | This fork vs [`sns-x-api`](https://github.com/maeplego/sns-x-api) (feed/ranking stays educational) |
| Auth hardening | Refresh tokens, `token_version`, logout-all, password change |
| Trust & safety | Reports, RBAC (user / moderator / admin), moderation APIs, audit log |
| Privacy | Account erasure endpoint + ops notes |
| Legal readiness | Signup `accept_terms` / `accept_privacy`, templates in [`docs/legal/`](docs/legal/) |
| Observability | `/health` · `/health/ready` · `/metrics`, optional Sentry, Grafana compose |
| Ops literacy | Backups, production checklist in [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| Cloud design (docs only) | [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md) + [`infra/`](infra/README.md) Terraform **skeleton** |

## Demo (local — preferred)

Pair with the frontend for a full walkthrough.

```bash
# Terminal 1 — API
cp .env.example .env
docker compose -f docker-compose.prod.yml up --build

# Terminal 2 — UI (other repo)
cd ../sns-x-frontend-prod
cp .env.example .env
npm install && npm run dev
```

| Check | URL / action |
|---|---|
| API up | http://localhost:8002/health and `/health/ready` |
| OpenAPI hidden in prod-like mode | `/docs` → 404 when `APP_ENV=production` |
| UI | http://localhost:5175 — signup (must accept terms/PP) → post → settings |
| Moderation | Sign up a second user as admin via DB/`role`, open `/moderation` |
| Metrics (optional) | `docker compose -f docker-compose.observability.yml up -d` → Grafana `:3000` |

**Suggested screenshots / short clip:** signup consent checkboxes → home feed → report a post → moderation console → `/metrics` or Grafana.

```bash
pip install -e ".[dev]"
pytest
```

## What this fork adds (changelog-style)

| Phase | Contents |
|---|---|
| **0** | Secret checks, liveness/readiness, hide OpenAPI in production |
| **1** | Access + refresh tokens, `token_version`, roles, Redis rate limits, RBAC deps |
| **2** | Reports, moderation (hide/suspend/labels/role), audit events |
| **3** | Metrics, TrustedHost, CI, backups, account erasure, ops doc |
| **Ops+** | Optional Sentry · Prometheus `/metrics` · Grafana compose stack |
| **Legal** | Signup requires legal acceptance; templates in [`docs/legal/`](docs/legal/) |
| **Infra docs** | AWS personal-scale design + Terraform skeleton (not a live deploy) |

## Legal docs (templates)

- [`docs/legal/TERMS.md`](docs/legal/TERMS.md) · [`PRIVACY.md`](docs/legal/PRIVACY.md) · [`CONTACT.md`](docs/legal/CONTACT.md)
- Version constants: `app/core/legal.py` — bump when you revise the docs
- **Templates only**, not legal advice

## Observability (optional)

```bash
# API must already be on :8002
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin / admin) — dashboard **sns-x-api-prod overview**
- Set `SENTRY_DSN` in `.env` to enable Sentry (disabled when empty)

## Ops & AWS design docs

- [docs/OPERATIONS.md](docs/OPERATIONS.md) — backup / restore / production checklist
- [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md) — personal-scale AWS architecture
- [docs/DEPLOY.md](docs/DEPLOY.md) — how you *would* deploy (runbook)
- [`infra/`](infra/README.md) — Terraform as **design material** (see below)

### Terraform status

`infra/` is a **portfolio / design skeleton**. It has not been applied to a real AWS account for this project, and is **not** a guarantee of a working one-click deploy. Treat it as structured documentation of a cost-aware layout (no NAT Gateway, Fargate + RDS + CloudFront), not as production infrastructure you must run.
