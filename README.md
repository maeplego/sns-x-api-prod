# sns-tutorial-x

個人開発 SNS バックエンドを **x-algorithm（X For You feed OSS）の設計思想** から学びながら、**コピペで実装できる** 連載です。

- **スコープ:** API のみ（curl / HTTPie / OpenAPI）
- **スタック:** FastAPI + PostgreSQL + Redis
- **進め方:** 各回の記事を上から順にコピペする。記事末尾にその回の完成形ファイルを掲載
- **タグ:** `v0.1` … `v1.3`（各回のテスト通過後に自動付与）

## シリーズ目次

| 回 | タイトル | Tag |
|---|---|---|
| 1 | [アーキテクチャの土台](articles/01-architecture.md) | `v0.1` |
| 2 | [API & DB & 認証](articles/02-api-db-auth.md) | `v0.2` |
| 3 | [タイムラインパイプライン（Pull）](articles/03-feed-pipeline.md) | `v0.3` |
| 4 | [Policy 層](articles/04-policy.md) | `v0.4` |
| 5 | [Ranking 層](articles/05-ranking.md) | `v0.5` |
| 6 | [Labeling Path](articles/06-labeling.md) | `v0.6` |
| 7 | [Plugin registry](articles/07-plugin-registry.md) | `v0.7` |
| 8 | [SideEffect & 通知](articles/08-side-effects.md) | `v0.8` |
| 9 | [Fan-out feed](articles/09-fanout-feed.md) | `v0.9` |
| 10 | [OutOfNetwork & pgvector](articles/10-out-of-network.md) | `v1.0` |
| 11 | [ミュート・採点前フィルタ・作者多様性](articles/11-mutes-filters-diversity.md) | `v1.1` |
| 12 | [返信 / スレッド](articles/12-replies-threads.md) | `v1.2` |
| 13 | [興味なし / 非表示](articles/13-not-interested.md) | `v1.3` |

## クイックスタート

```bash
cd sns-tutorial-x
cp .env.example .env
docker compose up --build
```

別ターミナル:

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"1.3.0"}
```

## 設計原則

1. **Request Path / Labeling Path を分離** — TL 表示と投稿後処理を混ぜない
2. **Policy ≠ Ranking** — 可視性と順序付けを別モジュールに
3. **起動時 fail-fast / 実行時 degrade** — 設定ミスは起動で落とし、任意 enrich 失敗は続行
4. **Feed = パイプライン段階** — home-mixer 型、Labeling = grox 型 plugin
