---
title: "個人開発 SNS を x-algorithm 流に設計する【第7回: Plugin registry 編】"
series: sns-tutorial-x
part: 7
slug: sns-tutorial-x/07-plugin-registry
tags: [FastAPI, plugin, registry]
---

# 個人開発 SNS を x-algorithm 流に設計する【第7回: Plugin registry 編】

**起点:** `git checkout v0.6`

## ゴール

- [ ] `@register` で Plan を足すと dispatcher を触らなくてよい
- [ ] `EngagementInitPlan` を **flows 配下だけ** に追加する
- [ ] 公開後に `post_engagement` 行ができる

**タグ:** `v0.7`

---

## 用語（この回で初登場）

### Plugin registry / 開放閉鎖原則

**開放閉鎖原則（OCP）:** 拡張には開いて、修正には閉じる。新しい後処理を足すとき `dispatcher.py` を書き換えない、が目標です。

x-algorithm の grox は `@register` + ディレクトリ走査で Plan を集めます。本連載の `load_all()` が `app/labeling/flows/` を再帰 import し、デコレータがクラスをリストに載せます。

### ORDER

同じイベントに複数 Plan があるときの実行順です。`post_publish` は 0、`engagement_init` は 100（公開後でないとカウンタ行を作れない）。

---

## やること

1. `PostEngagement` モデル + Alembic `003`
2. `app/labeling/flows/engagement/` に Plan と Task
3. `EngagementHydrator` で TL に like_count を載せる
4. コアの dispatcher は **無変更**

```bash
pytest
```

`test_registry.py` は `["post_publish", "engagement_init"]` を期待します。

---

# 第7回 完成形

新規: `flows/engagement/*`, `003_add_post_engagement.py`, `tests/test_registry.py`

変更: `models.py` に `PostEngagement`、`pipeline.py` に `EngagementHydrator`、version `0.7.0`

全文は `git checkout v0.7`。

---

**シリーズ:** [第6回](06-labeling.md) ← **第7回** → [第8回](08-side-effects.md)
