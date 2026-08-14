---
title: "個人開発 SNS を x-algorithm 流に設計する【第4回: Policy 編】"
series: sns-tutorial-x
part: 4
slug: sns-tutorial-x/04-policy
tags: [FastAPI, SNS, Policy]
---

# 個人開発 SNS を x-algorithm 流に設計する【第4回: Policy 編】

**起点:** `git checkout v0.3`

## ゴール

- [ ] Policy を Ranking から独立した Rule リストにする
- [ ] ブロックした作者の投稿を TL から落とす
- [ ] フォロワー限定投稿はフォロー解除後に見えない

**タグ:** `v0.4`

---

## 用語（この回で初登場）

### Policy / visibility-filtering

「**見せるか、見せないか**」だけを決める層です。x-algorithm では visibility-filtering が Ranking と別 crate です。スコアを下げるのではなく、候補そのものを捨てます。

### Rule / Chain of Responsibility

各ルールは `ALLOW` か `DROP` を返します。1 つでも DROP なら即終了です。これは **Chain of Responsibility**（責任の連鎖）に近いパターンです。新しい禁止条件は Rule クラスを足すだけで、パイプライン本体は触りません。

### Source は広く、Policy で絞る

Source が「フォロー中」だけ返すと、ブロック後も SQL 条件を増やし続けることになります。ブロックは **viewer 固有** なので Policy に置きます。第10回のおすすめ投稿でも同じ原則が効きます。

---

## Step 1: `blocks` テーブル

モデル `Block` と Alembic `002` を追加。API は `POST/DELETE /blocks/{user_id}`。

## Step 2: エンジン

`app/policy/engine.py`:

```python
class PolicyVerdict(str, enum.Enum):
    ALLOW = "allow"
    DROP = "drop"

def evaluate_rules(rules, context):
    for rule in rules:
        if rule.evaluate(context) == PolicyVerdict.DROP:
            return PolicyVerdict.DROP, rule.name
    return PolicyVerdict.ALLOW, None
```

## Step 3: ルール

- `BlockedAuthorRule`
- `SuspendedAuthorRule`
- `PrivateAccountRule`
- `FollowersOnlyPostRule`

## Step 4: パイプラインに挟む

Hydrator のあと、Selector の前:

```
... → AuthorHydrator → PolicyFilter → CursorSelector
```

`BlockedUserIdsQueryHydrator` でブロック ID を先に集めます。`AuthorHydrator` に `is_private` / `status` を足します。

version を `0.4.0` に。

```bash
pytest
```

---

# 第4回 完成形

新規: `app/policy/engine.py`, `rules.py`, `app/request/routers/blocks.py`, `alembic/versions/002_add_blocks.py`, `tests/test_policy.py`

変更: `models.py` に `Block`、`types.py` に `blocked_user_ids` と作者フラグ、`pipeline.py` に PolicyFilter、`main.py` に blocks ルーター、version `0.4.0`。

全文は `git checkout v0.4`。

---

**シリーズ:** [第3回](03-feed-pipeline.md) ← **第4回** → [第5回](05-ranking.md)
