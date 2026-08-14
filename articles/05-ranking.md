---
title: "個人開発 SNS を x-algorithm 流に設計する【第5回: Ranking 編】"
series: sns-tutorial-x
part: 5
slug: sns-tutorial-x/05-ranking
tags: [FastAPI, SNS, Ranking]
---

# 個人開発 SNS を x-algorithm 流に設計する【第5回: Ranking 編】

**起点:** `git checkout v0.4`

## ゴール

- [ ] 重みを YAML に外出しする
- [ ] Policy のあとでスコア順に並べる
- [ ] `/feed` が `rank_score` を返す

**タグ:** `v0.5`

---

## 用語（この回で初登場）

### Ranking / 線形スコア

「見せるものは決まった。**何順か**」が Ranking です。本連載は単純な **加重和** です。

```
score = w_recency * recency + w_in_network * in_network + ...
```

本番の ML ランカー（Phoenix など）と同じ「シグナル × 重み」の形です。

### シグナル

候補から計算する数値です。**recency** は新しいほど 1 に近い `1 / (1 + 経過時間)`。**in_network_boost** はフォロー中なら 1。**engagement** は `log(1 + いいね)` で、件数が爆発してもスコアが無限大にならないようにします。

### weights.yaml をコードの外に置く理由

重みを変えるたびにデプロイしなくてよくするためです。起動時にファイルが無い・キー欠けなら **fail-fast** します。

### YAML

人間が読みやすい設定ファイル形式です。Python では PyYAML で読みます。

---

## 実装

1. `ranking/weights.yaml` を置く
2. `app/ranking/weights.py` で必須キー検査
3. `app/ranking/scorer.py` でスコア計算
4. パイプライン: Policy のあと Ranker、Selector の前
5. `FeedPostItem.rank_score` をレスポンスに含める
6. 起動時 `load_weights()`（テスト以外）

```
... → PolicyFilter → Ranker → CursorSelector
```

```bash
pip install -e ".[dev]"
pytest
```

---

# 第5回 完成形

新規: `ranking/weights.yaml`, `app/ranking/weights.py`, `scorer.py`, `tests/test_ranking.py`

変更: `pipeline.py` に Ranker、`types.py` / `schemas.py` にスコア、`main.py` で `load_weights()`、version `0.5.0`、`pyproject.toml` に `pyyaml`。

全文は `git checkout v0.5`。

---

**シリーズ:** [第4回](04-policy.md) ← **第5回** → 第6回
