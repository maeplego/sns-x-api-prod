# sns-x-api

Fork of `sns-tutorial-x-api` with indie Visibility Filtering, ranking tweaks, and Under the Hood.

## New in this fork

- Safety labels: `spam_suspect` / `nsfw` / `do_not_amplify` (OON / For You out-of-network drops)
- Account `cred_score` (Agatha / user-cred lite)
- Ranking: OON discount, low-cred penalty, stronger author diversity
- Embedding retrieval: mute / label / similarity floor / per-author cap
- `GET /under-the-hood` transparency report

## Run

```bash
docker compose up --build
```

API: http://localhost:8001 (host) — does not collide with tutorial on 8000.

Upstream tutorial remote: `upstream` → `sns-tutorial-x-api`.
