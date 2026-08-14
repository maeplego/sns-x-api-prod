---
title: "個人開発 SNS を x-algorithm 流に設計する【第10回: OutOfNetwork & pgvector & Blender 編】"
series: sns-tutorial-x
part: 10
slug: sns-tutorial-x/10-out-of-network
tags: [FastAPI, pgvector, recommendations]
---

# 個人開発 SNS を x-algorithm 流に設計する【第10回: OutOfNetwork & pgvector & Blender 編】

**起点:** `git checkout v0.9`

## ゴール

- [ ] 投稿本文の embedding を Labeling Path で生成
- [ ] OutOfNetworkSource で類似投稿を取る
- [ ] SourceBlender で Thunder + OON を合成
- [ ] **v1.0 完成**

**タグ:** `v1.0`

---

## 用語（この回で初登場）

### embedding / ベクトル

文章を **固定長の数値の並び** にしたものです。近い意味の文章は、近いベクトルになります。本連載は ML モデルの代わりに、決定論的なハッシュで 384 次元を作ります。本番では sentence-transformers などに差し替えます。

### pgvector

PostgreSQL にベクトル型と類似検索を足す拡張です。`CREATE EXTENSION vector`。インデックスは **HNSW**（近似近傍探索。全部を比較せず近いものを速く探す）。

演算子 `<=>` はコサイン距離です。距離が小さいほど似ています。

### OutOfNetwork（OON）

フォローしていない人の投稿です。For You の「おすすめ」側です。Source は広く取り、Policy がブロックや非公開を落とします。

### Blender

複数 Source の候補を **重複除去と比率** で混ぜる段階です。Thunder（フォロー中）を優先し、OON はページの約 30% まで。home-mixer の Mixer/Blender の縮小版です。

### コサイン類似度

2 つのベクトルの向きの近さです。同じ文なら 1.0。テストでは Python 側で計算し、本番 Postgres では pgvector を使います。

---

## 実装順

1. Docker を `pgvector/pgvector:pg16` に変更
2. `post_embeddings` + Alembic `006` + HNSW
3. `EmbeddingPlan` ORDER=25
4. `ViewerInterestQueryHydrator`（自分の TL 投稿の平均ベクトル）
5. `OutOfNetworkSource` + `SourceBlender`
6. Ranking に `similarity: 0.20`

Plan 順: publish(0) → embedding(25) → fanout(50) → engagement(100)

```bash
pip install -e ".[dev]"
pytest
```

---

# 第10回 完成形

新規: `embedding_models.py`, `app/embedding/*`, `flows/embedding/*`, `blender.py`, `006_*.py`, `tests/test_blender.py`, `test_embedding.py`, `test_oon_feed.py`

変更: pipeline に OON + Blender、weights.yaml に similarity、version `1.0.0`、`pyproject.toml` に pgvector

全文は `git checkout v1.0`。

---

**シリーズ:** [第9回](09-fanout-feed.md) ← **第10回** → [第11回](11-mutes-filters-diversity.md)
