---
title: "個人開発 SNS を x-algorithm 流に設計する【第6回: Labeling Path 編】"
series: sns-tutorial-x
part: 6
slug: sns-tutorial-x/06-labeling
tags: [FastAPI, Redis, Worker]
---

# 個人開発 SNS を x-algorithm 流に設計する【第6回: Labeling Path 編】

**起点:** `git checkout v0.5`

## ゴール

- [ ] `POST /posts` が **202 Accepted** + `status=processing` を返す
- [ ] Worker が裏で `published` にする
- [ ] テストでは同期実行（InlineEventBus）

**タグ:** `v0.6`

---

## 用語（この回で初登場）

### 202 Accepted

「受け付けた。まだ完了していない」という HTTP ステータスです。201 Created は「もう作った」。投稿公開を Request Path から外す合図です。

### メッセージキュー / Redis Streams

処理を「後でやる人」に渡す箱です。**Redis Streams** は Redis のログ型キューです。`XADD` で書き、Worker が `XREADGROUP` で読みます。**Consumer Group** は複数 Worker で同じメッセージを二重処理しないためのグループ名です。

### Worker

API とは別プロセスです。ユーザーは待ちません。`python -m app.labeling.worker`

### Plan / Task / DAG

x-algorithm の grox に倣います。

- **Task:** 1 作業（validate, publish）
- **Plan:** Task の集まりと依存関係
- **DAG（有向非巡回グラフ）:** 「validate が終わってから publish」のような一方向の依存。ループ禁止。

### デコレータ `@register`

クラス定義時に「この Plan を一覧へ登録」します。第7回で本格的に使います。第6回は `PostPublishPlan` 1 本です。

### InlineEventBus

テスト用の偽物キューです。`publish()` した瞬間に Worker 相当の処理を同じプロセスで走らせます。pytest で Redis を起動しなくてよくなります。

---

## 流れ

```
POST /posts
  → posts 行を status=processing で INSERT
  → Redis Streams に post.created
  → 202 を返す

Worker
  → ValidatePostTask → PublishPostTask
  → status=published
```

Task は `database.SessionLocal()` を **実行時に** 参照します（`from app.core import database`）。テストが SessionLocal を差し替えたあとも正しい DB を使えます。

```bash
pytest
```

Docker では `worker` サービスを追加します。

---

# 第6回 完成形

新規: `app/core/queue.py`, `registry.py`, `app/labeling/*`, `flows/post_publish/*`, `tests/test_labeling.py`

変更: `POST /posts` が 202、`conftest.py` が `load_all()` + InlineEventBus、`docker-compose.yml` に worker、version `0.6.0`。

既存テストの `201` は `202` に更新。全文は `git checkout v0.6`。

---

**シリーズ:** [第5回](05-ranking.md) ← **第6回** → [第7回](07-plugin-registry.md)
