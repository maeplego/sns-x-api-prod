# sns-tutorial-x

個人開発 SNS バックエンドを **x-algorithm（X For You feed OSS）の設計思想** から学びながら、**コピペで実装できる** 10 回連載です。

- **スコープ:** API のみ（curl / HTTPie / OpenAPI）
- **スタック:** FastAPI + PostgreSQL + Redis
- **進め方:** 各回の記事を上から順にコピペする。記事末尾にその回の完成形ファイルを掲載
- **タグ:** `v0.1` … `v1.0`（各回のテスト通過後に自動付与）

## シリーズ目次

| 回 | タイトル | Tag |
|---|---|---|
| 1 | [アーキテクチャの土台](articles/01-architecture.md) | `v0.1` |
| 2 | [API & DB & 認証](articles/02-api-db-auth.md) | `v0.2` |
| 3 | [タイムラインパイプライン（Pull）](articles/03-feed-pipeline.md) | `v0.3` |
| 4 | [Policy 層](articles/04-policy.md) | `v0.4` |
| 5 | Ranking 層 | `v0.5` |
| 6 | Labeling Path | `v0.6` |
| 7 | Plugin registry | `v0.7` |
| 8 | SideEffect & 通知 | `v0.8` |
| 9 | Fan-out feed | `v0.9` |
| 10 | OutOfNetwork & pgvector | `v1.0` |

## クイックスタート

```bash
cd sns-tutorial-x
cp .env.example .env
docker compose up --build
```

別ターミナル:

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

## 設計原則

1. **Request Path / Labeling Path を分離** — TL 表示と投稿後処理を混ぜない
2. **Policy ≠ Ranking** — 可視性と順序付けを別モジュールに
3. **起動時 fail-fast / 実行時 degrade** — 設定ミスは起動で落とし、任意 enrich 失敗は続行
4. **Feed = パイプライン段階** — home-mixer 型、Labeling = grox 型 plugin
