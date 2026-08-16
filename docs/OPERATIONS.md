# Operations

Short runbook for `sns-x-api-prod`.

## Backup

Postgres (from host, matching Compose ports):

```bash
# Linux / macOS
./scripts/backup_postgres.sh

# PowerShell
./scripts/backup_postgres.ps1
```

Or manually:

```bash
pg_dump -h localhost -p 5434 -U sns -d sns_x_prod -Fc -f backup.dump
```

Store dumps off-box. Rotate retention to match your RPO.

## Restore

```bash
pg_restore -h localhost -p 5434 -U sns -d sns_x_prod --clean --if-exists backup.dump
# then:
alembic upgrade head
```

## Deploy checklist

1. Set `APP_ENV=production`.
2. Set a random `JWT_SECRET` (≥32 chars). Rejected at startup if weak.
3. Set a strong `POSTGRES_PASSWORD` (not `sns` / `password`).
4. Set `CORS_ORIGINS` to real frontend origins only.
5. Set `ALLOWED_HOSTS` (comma-separated) so TrustedHostMiddleware is active.
6. Use `docker-compose.prod.yml` (uvicorn **without** `--reload`).
7. Run `alembic upgrade head` (Compose `api` command already does this).
8. Confirm `GET /health` and `GET /health/ready`.
9. Confirm `/docs` and `/openapi.json` return 404 in production.
10. Smoke-test login → refresh → logout-all.
11. Take a DB backup before the first production cutover.
12. Confirm security headers (`X-Content-Type-Options`, `X-Frame-Options`) on responses.
13. For Compose prod DB password, set `POSTGRES_PASSWORD` in `.env` to the same strong value the API uses (compose default is `sns-prod-local-change-me-32chars!!`).
14. Optional: set `SENTRY_DSN` (and frontend `VITE_SENTRY_DSN`) for error monitoring.
15. Optional observability: `docker compose -f docker-compose.observability.yml up -d` then open Grafana at http://localhost:3000 (admin/admin). Prometheus scrapes `host.docker.internal:8002/metrics`.
16. Before public launch: fill `docs/legal/*`, set frontend `VITE_OPERATOR_NAME` / `VITE_CONTACT_EMAIL`, and have counsel review the templates.
