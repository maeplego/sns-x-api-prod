---
title: "個人開発 SNS を x-algorithm 流に設計する【第8回: SideEffect & 通知 & 観測編】"
series: sns-tutorial-x
part: 8
slug: sns-tutorial-x/08-side-effects
tags: [FastAPI, SideEffect, observability]
---

# 個人開発 SNS を x-algorithm 流に設計する【第8回: SideEffect & 通知 & 観測編】

**起点:** `git checkout v0.7`

## ゴール

- [ ] `/feed` 返却後に impression を非同期記録
- [ ] いいねで作者に通知
- [ ] `X-Request-ID` を全ログに載せる

**タグ:** `v0.8`

---

## 用語（この回で初登場）

### SideEffect

home-mixer の最終段です。**レスポンスを待たせない付帯処理**。TL を返したあと「この投稿を見せた」と記録します。Labeling（重い後処理）とは別で、Request Path の末尾に置きます。

### FastAPI BackgroundTasks

レスポンス送信の直後にコルーチンを走らせる仕組みです。専用 DB セッション（`database.SessionLocal()`）を使います。リクエスト用セッションと混ぜると、レスポンス後に閉じられて失敗します。

### 観測性 / 分散トレーシングの入口

障害調査で「このリクエストのログ全部」を拾うために **request_id** を付けます。Middleware が `X-Request-ID` ヘッダを生成し、structlog のコンテキストに bind します。

### Middleware

すべてのリクエストの前後に挟まる層です。Starlette の `BaseHTTPMiddleware` を使います。

---

## 実装順

1. `likes` / `notifications` / `feed_impressions` テーブル（Alembic `004`）
2. `RequestIdMiddleware`
3. `POST /likes/{post_id}` → 通知
4. `GET /notifications`
5. `/feed` の BackgroundTasks
6. `SeenPostsQueryHydrator` → Ranking の `seen_penalty`

```bash
pytest
```

---

# 第8回 完成形

新規: `social_models.py`, `middleware.py`, `side_effects/`, `routers/likes.py`, `notifications.py`, `004_*.py`, `tests/test_side_effects.py`

変更: feed router に BackgroundTasks、pipeline に SeenPosts、main に middleware、version `0.8.0`

全文は `git checkout v0.8`。

---

**シリーズ:** [第7回](07-plugin-registry.md) ← **第8回** → [第9回](09-fanout-feed.md)
