---
title: "個人開発 SNS を x-algorithm 流に設計する【第9回: Fan-out feed 編】"
series: sns-tutorial-x
part: 9
slug: sns-tutorial-x/09-fanout-feed
tags: [FastAPI, fan-out, Thunder]
---

# 個人開発 SNS を x-algorithm 流に設計する【第9回: Fan-out feed 編】

**起点:** `git checkout v0.8`

## ゴール

- [ ] 公開時に `user_feed` へ fan-out（Labeling Path）
- [ ] `/feed` の Source を `ThunderSource` に差し替え
- [ ] フォロワー限定はフォロワー + 作者だけに書く

**タグ:** `v0.9`

---

## 用語（この回で初登場）

### Fan-out / Push モデル

投稿した瞬間に、各フォロワーの「自分の TL 箱」へ行をコピーします。読むときは自分の箱だけ見ればよいので、フォロー人数が増えても読み取りが速くなります。書くコストはフォロワー数に比例します（セleb 問題）。

### Thunder

x-algorithm で in-network 候補を返すサービス名です。本連載では `user_feed` テーブルがその縮小版です。

### ON CONFLICT DO NOTHING

同じ `(user_id, post_id)` を二度書いてもエラーにしない SQL です。チュートリアルのテスト用 SQLite では、既存行を `get` してスキップする実装にしています。

**新規フォローの過去投稿バックフィルは v0.9 ではやりません。** 公開時点のフォロワーだけが対象です。

---

## 実装

1. `UserFeedEntry` + Alembic `005`
2. `FanOutPlan` ORDER=50（publish のあと、engagement の前）
3. `ThunderSource` が `user_feed` を読む
4. `build_feed_pipeline` の Source を差し替え（Policy / Ranking はそのまま）

```bash
pytest
```

---

# 第9回 完成形

新規: `flows/fanout/*`, `005_add_user_feed.py`, `tests/test_fanout.py`

変更: `social_models.py` に `UserFeedEntry`、`pipeline.py` に `ThunderSource`、version `0.9.0`

Policy テストは「投稿前にフォローする」よう更新（fan-out は公開時点のフォロワーのみ）。

全文は `git checkout v0.9`。

---

**シリーズ:** [第8回](08-side-effects.md) ← **第9回** → [第10回](10-out-of-network.md)
