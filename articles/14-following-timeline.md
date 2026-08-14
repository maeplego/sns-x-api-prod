---
title: "個人開発 SNS を x-algorithm 流に設計する【第14回: Following 専用 TL 編】"
series: sns-tutorial-x
part: 14
slug: sns-tutorial-x/14-following-timeline
tags: [FastAPI, feed, Thunder, Following]
---

# 個人開発 SNS を x-algorithm 流に設計する【第14回: Following 専用 TL 編】

この連載は **上から順にコピペする** と動くチュートリアルです。途中のコードは「今足す断片」、記事末尾が **この回の完成形** です。

**起点:** `git checkout v1.3`

## この回のゴール

- [ ] `GET /feed` はこれまでどおり For You（Thunder + OON + Ranking）
- [ ] `GET /feed/following` は **フォロー中だけ**、新しい順
- [ ] Following には Ranker / OON / 会話の畳み込み / 48 時間カットを入れない
- [ ] ミュート・ブロック・非表示など **見せない** ルールは残す

**第14回終了時点のタグ:** `v1.4`

---

## 用語（この回で初登場）

### Surface / 面

同じ「ホーム」でも、画面が違えばパイプラインが違います。x-algorithm の Home Mixer は For You と Following を **別の Mixer** として組み立てます。ソース・並べ方・フィルタの組み合わせが面ごとに決まります。

本連載では:

| Surface | エンドポイント | 候補 | 並べ方 |
|---|---|---|---|
| For You | `GET /feed` | Thunder + OON | Ranker |
| Following | `GET /feed/following` | Thunder だけ | 新しい順 |

レスポンスの `surface` は、今どの面を返したかを明示します。クライアントが取り違えないためのラベルです。

### 時系列 TL でも Policy は残る

「フォローした人の投稿を新しい順」は Ranking を外す、という意味です。**見えないものは見えない** は Policy の仕事のままです。

Following で外すもの / 残すもの:

| | For You | Following |
|---|---|---|
| Thunder（`user_feed`） | 使う | 使う |
| OON / Blender | 使う | 使わない |
| Ranker | 使う | 使わない（`rank_score` は `null`） |
| 会話の畳み込み | 根があれば返信を落とす | 根も返信も出す |
| `AgeRule`（48 時間） | DROP | 使わない |
| `OonReplyRule` | ある | 不要（OON が無い） |
| ミュート / ブロック / hide | DROP | DROP |
| `SelfPostRule` | DROP | DROP |
| `ReplyAncillaryRule` | DROP | DROP |

おすすめは「新鮮さ」を強く見ます。Following は「この人を追っている」が約束なので、2 日前の投稿も出します。

---

## 前提

| 項目 | 内容 |
|---|---|
| 起点 | `v1.3` |
| 触る層 | Policy のルールセット、パイプラインの組み立て、フィード API |
| 触らない層 | Labeling Path、DB スキーマ、OON 検索そのもの |

新しいテーブルはありません。同じ `FeedPipeline` にスイッチを足して、組み立てを変えます。

---

## Step 1: パイプラインに「並べない」スイッチ

`FeedPipeline` に `rank: bool = True`。For You は今までどおり `rank_candidates`。Following は `created_at` の新しい順だけ。

`conversation_deduper=False` もここで使います。第12回の畳み込みは For You 専用でした。

```python
class FeedPipeline:
    def __init__(
        self,
        ...,
        blender: SourceBlender | None = None,
        conversation_deduper: bool = True,
        rank: bool = True,
    ):
        ...
        self.rank = rank

    async def run(self, db, query):
        ...
        if self.rank:
            for candidate in candidates:
                candidate.seen = candidate.id in query.seen_post_ids
            candidates = rank_candidates(query, candidates, self.weights)
        else:
            candidates.sort(key=lambda c: (c.created_at, c.id), reverse=True)
        if self.conversation_deduper:
            candidates = dedupe_conversations(candidates)
        ...
```

Blender が `None` のときは、ソースの結果をそのままつなぎます（Thunder 1 本なので実質そのバッチ）。

---

## Step 2: Following 用の Policy

`home_feed_policy()` は触りません。新しい関数を足します。

```python
def following_feed_policy() -> list[Rule]:
    """Chronological Following surface: no 48h cutoff, no OON reply rule."""
    return [
        HiddenPostRule(),
        SelfPostRule(),
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
        ReplyAncillaryRule(),
    ]
```

`AgeRule` が無いので、49 時間前の投稿も残ります。`OonReplyRule` は OON が無いので不要です。

QueryHydrator も面に合わせて間引きます。Following は類似投稿を取らないので `ViewerInterestQueryHydrator` と `SeenPostsQueryHydrator` は付けません。ミュート・ブロック・hide を読む hydrator は残します。

---

## Step 3: 組み立てと API

```python
def build_following_pipeline(weights: RankingWeights | None = None) -> FeedPipeline:
    resolved_weights = weights or load_weights()
    return FeedPipeline(
        query_hydrators=[
            FollowingQueryHydrator(),
            BlockedUserIdsQueryHydrator(),
            MutedUserIdsQueryHydrator(),
            MutedKeywordsQueryHydrator(),
            FeedbackQueryHydrator(),
        ],
        sources=[ThunderSource()],
        hydrators=[AuthorHydrator(), ParentHydrator(), EngagementHydrator()],
        policy=PolicyFilter(following_feed_policy()),
        weights=resolved_weights,
        selector=CursorSelector(),
        blender=None,
        conversation_deduper=False,
        rank=False,
    )
```

`GET /feed/following` を足し、レスポンスに `surface` を載せます。For You は `"for_you"`、Following は `"following"`。インプレッションの Side Effect は両面とも同じです（「見せた」事実は面が違っても残す）。

version は `1.4.0`。

```bash
pip install -e ".[dev]"
pytest
```

---

# 第14回 完成形

以下はこの回で新規または差し替えるファイルです。`pipeline.py` の全体は `git checkout v1.4`。

## `app/policy/rules.py` に追加

`home_feed_policy()` と `thread_policy()` のあいだへ。

```python
def following_feed_policy() -> list[Rule]:
    """Chronological Following surface: no 48h cutoff, no OON reply rule."""
    return [
        HiddenPostRule(),
        SelfPostRule(),
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
        ReplyAncillaryRule(),
    ]
```

## `app/request/feed/schemas.py`

```python
class FeedResponse(BaseModel):
    items: list[FeedPostItem]
    next_cursor: str | None = None
    surface: str = "for_you"
```

## `app/request/feed/pipeline.py` 断片

`FeedPipeline.__init__` に `rank: bool = True`。`run()` の Ranker ブロックを `if self.rank:` にし、`else` で新しい順ソート。末尾に `build_following_pipeline()`。

## `app/request/feed/router.py`（差し替え）

```python
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import database
from app.core.database import get_db
from app.core.models import User
from app.request.auth import get_current_user
from app.request.feed.pipeline import build_feed_pipeline, build_following_pipeline
from app.request.feed.schemas import FeedPostItem, FeedResponse
from app.request.feed.types import FeedCandidate, FeedQuery, decode_cursor
from app.request.side_effects.feed_impression import record_feed_impressions

router = APIRouter(tags=["feed"])
for_you_pipeline = build_feed_pipeline()
following_pipeline = build_following_pipeline()


async def _run_feed_impression_side_effect(viewer_id: uuid.UUID, post_ids: list[uuid.UUID]) -> None:
    async with database.SessionLocal() as db:
        await record_feed_impressions(db, viewer_id, post_ids)


def _parse_cursor(cursor: str | None):
    if cursor is None:
        return None
    try:
        return decode_cursor(cursor)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor",
        ) from exc


def _to_response(candidates: list[FeedCandidate], next_cursor: str | None, surface: str) -> FeedResponse:
    items = [
        FeedPostItem(
            id=c.id,
            author_id=c.author_id,
            author_handle=c.author_handle or "unknown",
            author_display_name=c.author_display_name or "Unknown",
            body=c.body,
            created_at=c.created_at,
            rank_score=c.rank_score,
            parent_id=c.parent_id,
        )
        for c in candidates
    ]
    return FeedResponse(items=items, next_cursor=next_cursor, surface=surface)


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    background_tasks: BackgroundTasks,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    query = FeedQuery(viewer_id=current_user.id, cursor=_parse_cursor(cursor), limit=limit)
    candidates, next_cursor = await for_you_pipeline.run(db, query)
    response = _to_response(candidates, next_cursor, "for_you")
    background_tasks.add_task(
        _run_feed_impression_side_effect,
        current_user.id,
        [item.id for item in response.items],
    )
    return response


@router.get("/feed/following", response_model=FeedResponse)
async def get_following_feed(
    background_tasks: BackgroundTasks,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedResponse:
    query = FeedQuery(viewer_id=current_user.id, cursor=_parse_cursor(cursor), limit=limit)
    candidates, next_cursor = await following_pipeline.run(db, query)
    response = _to_response(candidates, next_cursor, "following")
    background_tasks.add_task(
        _run_feed_impression_side_effect,
        current_user.id,
        [item.id for item in response.items],
    )
    return response
```

`main.py` / `/health` / `pyproject.toml` の version は `1.4.0`。

テスト: `tests/test_following_feed.py`。For You 側の既存テスト（OON・48 時間・会話の畳み込み）は触らず、Following との差分だけを足します。全文は `git checkout v1.4`。

---

**シリーズ:** [第13回](13-not-interested.md) ← **第14回** → [第15回](15-who-to-follow.md)
