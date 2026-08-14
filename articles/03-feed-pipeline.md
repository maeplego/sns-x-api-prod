---
title: "個人開発 SNS を x-algorithm 流に設計する【第3回: タイムラインパイプライン編】"
series: sns-tutorial-x
part: 3
slug: sns-tutorial-x/03-feed-pipeline
tags: [FastAPI, SNS, タイムライン, home-mixer]
---

# 個人開発 SNS を x-algorithm 流に設計する【第3回: タイムラインパイプライン編】

**起点:** `git checkout v0.2`

## この回のゴール

- [ ] `GET /feed` を段階パイプラインで実装する
- [ ] フォロー中ユーザーの投稿が TL に出る（Pull モデル）
- [ ] 各段階の所要時間をログに出す

**タグ:** `v0.3`

---

## 用語（この回で初登場）

### home-mixer / candidate-pipeline

x-algorithm で For You TL を組み立てる中心サービスが **home-mixer** です。候補を一度に全部混ぜず、**段階（stage）** に分けます。

```
QueryHydrator → Source → Hydrator → Policy → Ranking → Selector → SideEffect
```

第3回は前半 4 段階だけです（Policy / Ranking / SideEffect は後の回）。

### QueryHydrator

「投稿を取る前に、リクエスト文脈を集める」段階です。フォロー ID、後の回ではブロック一覧や既読 ID をここで載せます。

### Source

候補投稿の **供給源** です。第3回は `InNetworkSource`（フォロー中の投稿を SQL でその場取得 = **Pull**）。第9回で fan-out キャッシュ（Thunder）に差し替えます。

### Hydrator

候補に足りない情報を足す段階です。作者の handle など。見つからなければ `"unknown"` で続行（degrade）。

### Selector / カーソルページネーション

返す件数を切る段階です。**compound cursor** は `(created_at, post_id)` の組で「この投稿より古いページ」を表します。オフセット `OFFSET 40` より安定します。

### ABC（抽象基底クラス）

`QueryHydrator` などはインターフェースです。中身の実装を後から差し替えても、パイプライン本体は変わりません。**Strategy パターン**（アルゴリズムをオブジェクトとして差し替える）に近いです。

### Pull モデル vs Push（fan-out）

- **Pull:** 読むときに「フォロー中の投稿」を検索する
- **Push / fan-out:** 書くときに各フォロワーの箱へコピーする（第9回）

---

## Step 1: 型

`app/request/feed/types.py` を新規作成します。

```python
@dataclass
class FeedQuery:
    viewer_id: uuid.UUID
    following_ids: set[uuid.UUID] = field(default_factory=set)
    cursor: tuple[datetime, uuid.UUID] | None = None
    limit: int = 20
```

`FeedCandidate` はパイプライン内部の候補です。API レスポンス（`FeedPostItem`）とは分けます。

---

## Step 2: 各段階

`pipeline.py` にインターフェースと実装を置きます。

**FollowingQueryHydrator** — `follows` から followee_id を取り、自分の ID も足します（自分の投稿も TL に出る）。

**InNetworkSource** — `author_id IN following_ids` かつ `published` かつ未削除。`limit + 1` 件取って「次ページがあるか」を判定します。

**AuthorHydrator** — `User.id IN (...)` を 1 クエリ。

**CursorSelector** — 先頭 `limit` 件を返し、余りがあれば cursor 文字列を返す。

---

## Step 3: FeedPipeline.run

段階を順番に呼び、`duration_ms` を structlog に出します。

```python
def build_feed_pipeline() -> FeedPipeline:
    return FeedPipeline(
        query_hydrators=[FollowingQueryHydrator()],
        sources=[InNetworkSource()],
        hydrators=[AuthorHydrator()],
        selector=CursorSelector(),
    )
```

---

## Step 4: ルーター

`GET /feed` を `app/request/feed/router.py` に作り、`main.py` で `include_router` します。version は `0.3.0`。

認証必須です。未ログインなら 401。

---

## Step 5: テスト

Alice が Bob をフォロー → Bob が投稿 → Alice の `/feed` に 1 件。

```bash
pytest
```

---

## チェックリスト

- [ ] `GET /feed` が動く
- [ ] フォローした人の投稿だけ見える（自分の投稿も含む）
- [ ] `pytest` 成功

---

## 次回予告

**第4回: Policy** — ブロック・フォロワー限定を「見せない」ルールとして Ranking から分離します。

---

# 第3回 完成形

新規: `app/request/feed/types.py`, `schemas.py`, `pipeline.py`, `router.py`, `__init__.py`, `tests/test_feed.py`

変更: `app/main.py` に `feed_router` を追加し version `0.3.0`。`pyproject.toml` / `test_health.py` も `0.3.0`。

完成形の全文はタグ `v0.3` と一致します。

```bash
git checkout v0.3
pytest
```

`main.py` の差分ポイント:

```python
from app.request.feed.router import router as feed_router
# ...
app.include_router(feed_router)
```

---

**シリーズ:** [第2回](02-api-db-auth.md) ← **第3回** → 第4回
