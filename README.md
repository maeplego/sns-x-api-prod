# sns-x-api-prod

**Production-oriented fork** of the learning/product repo [`sns-x-api`](https://github.com/maeplego/sns-x-api). Do **not** patch hardening work back into the learning repo — keep that tree focused on feed/ranking education.

| | |
|---|---|
| Package | `sns-x-api-prod` `3.0.7` |
| Stack | FastAPI / PostgreSQL (pgvector) / Redis / Alembic |
| Compose ports | API `8002` · Postgres `5434` · Redis `6381` · DB `sns_x_prod` |
| Frontend | [`sns-x-frontend-prod`](https://github.com/maeplego/sns-x-frontend-prod) on `:5175` |
| CI | `.github/workflows/ci.yml` → **pytest only** (not a deploy pipeline) |
| License | MIT — filing / x-algorithm notes: see learning [`sns-x-api/README.md`](https://github.com/maeplego/sns-x-api) |

> **Portfolio note:** This stack shows production *thinking* (auth, moderation, legal consent, ops, AWS design). It is **not** required to run on a public AWS account. Local Compose is the intended demo.

## What this repo demonstrates

| Theme | Where to look |
|---|---|
| Learning vs product split | This fork vs [`sns-x-api`](https://github.com/maeplego/sns-x-api) |
| Auth hardening | Refresh tokens, `token_version`, logout-all, password change |
| Trust & safety | Reports, RBAC, moderation APIs, audit log |
| Privacy | Account erasure (`DELETE /users/me` soft-anonymize) |
| Legal readiness | Signup stores `terms_version` + `privacy_version`; templates in [`docs/legal/`](docs/legal/) |
| Observability | `/health` · `/health/ready` · **unauthenticated** `/metrics` (local scrape); optional Sentry |
| Ops literacy | Backups, checklist in [`docs/OPERATIONS.md`](docs/OPERATIONS.md) |
| Cloud design (docs only) | [`docs/INFRASTRUCTURE.md`](docs/INFRASTRUCTURE.md) + [`infra/`](infra/README.md) |
| Feed education history | [`articles/`](articles/README.md) — **tutorial copies**, not current ports/versions |

## Demo (local — preferred)

```bash
# Terminal 1 — API (default: APP_ENV=development from .env.example)
cp .env.example .env
docker compose -f docker-compose.prod.yml up --build
# Note: compose.prod = uvicorn without --reload; it still bind-mounts code for local iteration.

# Terminal 2 — UI
cd ../sns-x-frontend-prod
cp .env.example .env
# Optional for contact page screenshots:
# VITE_OPERATOR_NAME=...  VITE_CONTACT_EMAIL=...
npm install && npm run dev
```

| Check | URL / action |
|---|---|
| API up | http://localhost:8002/health · `/health/ready` |
| UI | http://localhost:5175 — signup (terms/PP checks) → post → settings (shows user id) |
| Report → moderation | **Two accounts** — see below |
| Metrics (optional) | `docker compose -f docker-compose.observability.yml up -d` → Grafana `:3000` |
| Under the Hood | UI `/under-the-hood` (ranking explanation surface) |

### Prod-like local mode (optional)

Default `.env.example` keeps `APP_ENV=development` (OpenAPI `/docs` stays on). To exercise production gates:

```bash
# In .env — must not use the example JWT_SECRET (rejected in production)
APP_ENV=production
POSTGRES_PASSWORD=sns-prod-local-change-me-32chars!!
JWT_SECRET=$(openssl rand -base64 48)   # PowerShell: use a long random string
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost:5175
```

Then restart Compose and confirm `/docs` → **404**. Keep Postgres password aligned with the Compose DB service password.

### Moderation walkthrough (two users)

1. **User A** signs up, creates a post.
2. **User B** signs up in another browser/profile, opens A’s post → **通報** (own posts cannot be reported).
3. Promote B (or A) to admin in Postgres (`5434` / db `sns_x_prod` / user `sns`):

```sql
UPDATE users SET role = 'admin' WHERE handle = 'user_b_handle';
```

4. In the UI: open **設定**, confirm role after **re-login** or full refresh of `/users/me` (cached client role). Nav shows **モデレーション**.
5. Open `/moderation` — review reports. Admin “ロール付与” needs the target **ユーザー ID** (shown on 設定).

```bash
pip install -e ".[dev]"
pytest
```

## What this fork adds (changelog-style)

| Phase | Contents |
|---|---|
| **0** | Secret checks, liveness/readiness, hide OpenAPI in production |
| **1** | Access + refresh tokens, `token_version`, roles, Redis rate limits, RBAC |
| **2** | Reports, moderation, audit events |
| **3** | Metrics, TrustedHost, pytest CI, backups, account erasure, ops doc |
| **Ops+** | Optional Sentry · Prometheus `/metrics` · Grafana compose |
| **Legal** | Signup legal acceptance + version columns |
| **Infra docs** | AWS design + Terraform skeleton (**not applied**) |

## Legal docs (templates)

- [`docs/legal/TERMS.md`](docs/legal/TERMS.md) · [`PRIVACY.md`](docs/legal/PRIVACY.md) · [`CONTACT.md`](docs/legal/CONTACT.md)
- Versions: `app/core/legal.py` — bump when revising docs
- **Templates only**, not legal advice

## Observability (optional)

```bash
docker compose -f docker-compose.observability.yml up -d
```

- Prometheus: http://localhost:9090 · Grafana: http://localhost:3000 (admin/admin)
- `/metrics` has **no auth** — fine behind localhost/Docker network; do not expose raw on the public internet without an edge ACL
- `SENTRY_DSN` enables Sentry when set

## Ops & AWS design docs

- [docs/OPERATIONS.md](docs/OPERATIONS.md)
- [docs/INFRASTRUCTURE.md](docs/INFRASTRUCTURE.md)
- [docs/DEPLOY.md](docs/DEPLOY.md) — hypothetical deploy runbook; **no GitHub Actions deploy workflows in this repo**
- [`infra/`](infra/README.md) — Terraform **design material** (never applied for this portfolio)

### CI vs deploy

| In repo today | Not in repo |
|---|---|
| `ci.yml` → install + `pytest` | ECR build, ECS deploy, Terraform apply Actions |
| FE repo: Playwright smoke + `npm run build` | Live AWS environment |
