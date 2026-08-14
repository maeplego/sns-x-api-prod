---
title: "個人開発 SNS を x-algorithm 流に設計する【第11回: ミュート・採点前フィルタ・作者多様性編】"
series: sns-tutorial-x
part: 11
slug: sns-tutorial-x/11-mutes-filters-diversity
tags: [FastAPI, Policy, Ranking, mute]
---

# 個人開発 SNS を x-algorithm 流に設計する【第11回: ミュート・採点前フィルタ・作者多様性編】

この連載は **上から順にコピペする** と動くチュートリアルです。途中のコードは「今足す断片」、記事末尾が **この回の完成形** です。

**起点:** `git checkout v1.0`

## この回のゴール

- [ ] アカウントミュートとキーワードミュートを Policy で DROP する
- [ ] 自分の投稿と 48 時間より古い投稿を採点前に落とす
- [ ] 同じ作者の連投を Ranking で減衰する（作者多様性）
- [ ] ミュートはフォローを切らない（ブロックとの違い）

**第11回終了時点のタグ:** `v1.1`

---

## 用語（この回で初登場）

### ミュート vs ブロック

| | ブロック | ミュート |
|---|---|---|
| 関係 | 切りたい | 残してよい |
| TL | 見せない | 見せない |
| フォロー | 多くの製品では解除する | **維持する** |

x-algorithm の `AuthorSocialgraphFilter` は block **と** mute の両方を落とします。違いはソーシャルグラフ側です。ミュートを解除すれば、fan-out 済みの `user_feed` から **再計算なしで** 再表示できます。だから Mute は Labeling ではなく Request Path の Policy です。

### キーワードミュート / `MutedKeywordFilter`

本文に特定の文字列が含まれる投稿を落とします。本連載は **小文字化した部分一致** です。本番では単語境界や言語トークンの方が誤爆が減ります。

### Pre-scoring filter

x-algorithm はスコア計算の **前** に候補を落とす段を持ちます。

- `AgeFilter` — 48 時間より古い投稿
- `SelfTweetFilter` — 閲覧者自身の投稿（For You は「おすすめ」であり、自分の投稿置き場ではない）

本連載は新しい層を増やしません。問いが「見せるか？」なら **Policy の Rule** に足します。Ranking に `score *= 0` を書かない、という第1回の約束を守ります。

### 作者多様性 / `AuthorDiversityScorer`

独立に採点したあと、**同じ作者の 2 本目以降** に減衰を掛けます。1 人の連投で TL が埋まらないようにするためです。見せない（Policy）のではなく、順番を変える（Ranking）ので `scorer.py` に置きます。

```
1 本目: score × 1.0
2 本目: score × decay
3 本目: score × decay²   （floor を下回らない）
```

減衰の前にスコア順へ並べるので、その作者の **一番強い投稿** が 1 本目になります。

---

## 前提

| 項目 | 内容 |
|---|---|
| 起点 | `v1.0`（第10回完了） |
| 触る層 | Policy（DROP）と Ranking（減衰）。Labeling は触らない |

パイプライン（この回のあと）:

```
QueryHydrator（follow / block / mute / keyword / seen / interest）
  → Thunder + OON → Blender → Hydrator
  → PolicyFilter（self / age / block / mute / keyword / …）
  → Ranker（加重和 → 作者多様性）
  → CursorSelector
```

---

## Step 1: `mutes` と `muted_keywords`

`Block` の隣に `Mute` を足します。キーワードは閲覧者の設定なので `social_models.py` です。

API:

| メソッド | パス | 意味 |
|---|---|---|
| `POST` | `/mutes/{user_id}` | アカウントをミュート |
| `GET` | `/mutes` | 一覧 |
| `DELETE` | `/mutes/{user_id}` | 解除 |
| `POST` | `/muted-keywords` | `{"keyword": "crypto"}`（保存時に小文字化） |
| `GET` | `/muted-keywords` | 一覧 |
| `DELETE` | `/muted-keywords/{keyword_id}` | 解除 |

自分自身はミュートできません。Alembic は `007` です。

---

## Step 2: QueryHydrator と Policy Rule

`MutedUserIdsQueryHydrator` と `MutedKeywordsQueryHydrator` で、viewer 固有の集合を先に集めます。Source の SQL に `NOT IN (muted…)` を足さないでください。第4回と同じく **Source は広く、Policy で絞る** です。

新しい Rule:

- `SelfPostRule` — `author_id == viewer_id` なら DROP
- `AgeRule` — 経過が 48 時間超なら DROP
- `MutedAuthorRule`
- `MutedKeywordRule` — `keyword in body.lower()`

`home_feed_policy()` の先頭に self / age を置きます。安いチェックを先にすると、ログに残る rule 名も読みやすくなります。x-algorithm と同様、**最初の DROP で打ち切り** です。

`PrivateAccountRule` には「自分の投稿は ALLOW」が残っています。For You では `SelfPostRule` が先に落とすので死に分岐です。プロフィール TL（自分の投稿を見せる面）を足すときに同じ Rule を使い回せます。

---

## Step 3: 作者多様性

`ranking/weights.yaml` にシグナルではない 2 キーを足します。起動時の fail-fast 対象です。

```yaml
author_diversity_decay: 0.50
author_diversity_floor: 0.25
```

`rank_candidates` は (1) 候補ごとに独立スコア (2) スコア順 (3) 作者ごとに減衰 (4) 再ソート、です。Phoenix の「候補同士が注意し合わない」に対応する個人開発版で、減衰だけが他候補を見ます。

---

## Step 4: パイプラインに接続

`build_feed_pipeline()` の QueryHydrator リストに mute 系を足し、`PolicyFilter` が `muted_user_ids` / `muted_keywords` を context に渡すようにします。`main.py` でルータを include。version は `1.1.0`。

```bash
pip install -e ".[dev]"
pytest
```

全部通ればこの回は完了です。

---

# 第11回 完成形

以下は **この回で新規または中身を差し替えるファイル** です。変更の大きい `pipeline.py` は断片のあと、全文は `git checkout v1.1`。

## `app/core/models.py`（`Block` の直後に追加）

```python
class Mute(Base):
    """Hide an account without breaking the follow edge (unlike Block)."""

    __tablename__ = "mutes"
    __table_args__ = (UniqueConstraint("muter_id", "muted_id", name="uq_mutes_pair"),)

    muter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    muted_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

## `app/core/social_models.py`（先頭付近に追加）

```python
class MutedKeyword(Base):
    __tablename__ = "muted_keywords"
    __table_args__ = (
        UniqueConstraint("user_id", "keyword", name="uq_muted_keywords_user_keyword"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True
    )
    keyword: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

## `alembic/versions/007_add_mutes.py`

```python
"""add mutes and muted_keywords

Revision ID: 007
Revises: 006
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mutes",
        sa.Column("muter_id", sa.UUID(), nullable=False),
        sa.Column("muted_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["muted_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["muter_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("muter_id", "muted_id"),
        sa.UniqueConstraint("muter_id", "muted_id", name="uq_mutes_pair"),
    )
    op.create_table(
        "muted_keywords",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("keyword", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "keyword", name="uq_muted_keywords_user_keyword"),
    )
    op.create_index("ix_muted_keywords_user_id", "muted_keywords", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_muted_keywords_user_id", table_name="muted_keywords")
    op.drop_table("muted_keywords")
    op.drop_table("mutes")
```

## `app/request/schemas.py`（`BlockResponse` の直後）

```python
class MuteResponse(BaseModel):
    muter_id: uuid.UUID
    muted_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MutedKeywordCreateRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=64)

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("keyword must not be blank")
        return normalized


class MutedKeywordResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    keyword: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

## `app/request/routers/mutes.py`（新規・全文）

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import Mute, User
from app.request.auth import get_current_user
from app.request.schemas import MuteResponse

router = APIRouter(prefix="/mutes", tags=["mutes"])


@router.post("/{user_id}", response_model=MuteResponse, status_code=status.HTTP_201_CREATED)
async def mute_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Mute:
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot mute yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.execute(
        select(Mute).where(
            Mute.muter_id == current_user.id,
            Mute.muted_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already muted")

    mute = Mute(muter_id=current_user.id, muted_id=user_id)
    db.add(mute)
    await db.commit()
    await db.refresh(mute)
    return mute


@router.get("", response_model=list[MuteResponse])
async def list_mutes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Mute]:
    result = await db.execute(select(Mute).where(Mute.muter_id == current_user.id))
    return list(result.scalars().all())


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unmute_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(Mute).where(
            Mute.muter_id == current_user.id,
            Mute.muted_id == user_id,
        )
    )
    mute = result.scalar_one_or_none()
    if mute is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not muted")

    await db.delete(mute)
    await db.commit()
```

## `app/request/routers/muted_keywords.py`（新規・全文）

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.models import User
from app.core.social_models import MutedKeyword
from app.request.auth import get_current_user
from app.request.schemas import MutedKeywordCreateRequest, MutedKeywordResponse

router = APIRouter(prefix="/muted-keywords", tags=["muted-keywords"])


@router.post("", response_model=MutedKeywordResponse, status_code=status.HTTP_201_CREATED)
async def create_muted_keyword(
    payload: MutedKeywordCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MutedKeyword:
    existing = await db.execute(
        select(MutedKeyword).where(
            MutedKeyword.user_id == current_user.id,
            MutedKeyword.keyword == payload.keyword,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Keyword already muted")

    row = MutedKeyword(user_id=current_user.id, keyword=payload.keyword)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("", response_model=list[MutedKeywordResponse])
async def list_muted_keywords(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MutedKeyword]:
    result = await db.execute(
        select(MutedKeyword).where(MutedKeyword.user_id == current_user.id)
    )
    return list(result.scalars().all())


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_muted_keyword(
    keyword_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        select(MutedKeyword).where(
            MutedKeyword.id == keyword_id,
            MutedKeyword.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keyword not found")

    await db.delete(row)
    await db.commit()
```

## `app/policy/engine.py`（差し替え・全文）

`PolicyContext` にミュート集合と、AgeRule テスト用の `now` を足します。

```python
import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.request.feed.types import FeedCandidate


class PolicyVerdict(str, enum.Enum):
    ALLOW = "allow"
    DROP = "drop"


@dataclass(frozen=True)
class PolicyContext:
    viewer_id: uuid.UUID
    following_ids: set[uuid.UUID]
    blocked_user_ids: set[uuid.UUID]
    candidate: FeedCandidate
    muted_user_ids: set[uuid.UUID] = field(default_factory=set)
    muted_keywords: set[str] = field(default_factory=set)
    now: datetime | None = None


class Rule:
    name: str

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        raise NotImplementedError


def evaluate_rules(
    rules: list[Rule], context: PolicyContext
) -> tuple[PolicyVerdict, str | None]:
    for rule in rules:
        if rule.evaluate(context) == PolicyVerdict.DROP:
            return PolicyVerdict.DROP, rule.name
    return PolicyVerdict.ALLOW, None
```

## `app/policy/rules.py`（差し替え・全文）

```python
from datetime import UTC, datetime

from app.core.models import PostVisibility, UserStatus
from app.policy.engine import PolicyContext, PolicyVerdict, Rule

MAX_AGE_HOURS = 48


class SelfPostRule(Rule):
    name = "SelfPostRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id == context.viewer_id:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class AgeRule(Rule):
    name = "AgeRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        now = context.now or datetime.now(UTC)
        created_at = context.candidate.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        age_hours = (now - created_at).total_seconds() / 3600.0
        if age_hours > MAX_AGE_HOURS:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class BlockedAuthorRule(Rule):
    name = "BlockedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id in context.blocked_user_ids:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class MutedAuthorRule(Rule):
    name = "MutedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_id in context.muted_user_ids:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class MutedKeywordRule(Rule):
    name = "MutedKeywordRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        body = context.candidate.body.lower()
        for keyword in context.muted_keywords:
            if keyword and keyword in body:
                return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class SuspendedAuthorRule(Rule):
    name = "SuspendedAuthorRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.author_status == UserStatus.SUSPENDED:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class PrivateAccountRule(Rule):
    name = "PrivateAccountRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        author_id = context.candidate.author_id
        if author_id == context.viewer_id:
            return PolicyVerdict.ALLOW
        if not context.candidate.author_is_private:
            return PolicyVerdict.ALLOW
        if author_id in context.following_ids:
            return PolicyVerdict.ALLOW
        return PolicyVerdict.DROP


class FollowersOnlyPostRule(Rule):
    name = "FollowersOnlyPostRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.visibility != PostVisibility.FOLLOWERS_ONLY:
            return PolicyVerdict.ALLOW
        author_id = context.candidate.author_id
        if author_id == context.viewer_id:
            return PolicyVerdict.ALLOW
        if author_id in context.following_ids:
            return PolicyVerdict.ALLOW
        return PolicyVerdict.DROP


def home_feed_policy() -> list[Rule]:
    return [
        SelfPostRule(),
        AgeRule(),
        BlockedAuthorRule(),
        MutedAuthorRule(),
        MutedKeywordRule(),
        SuspendedAuthorRule(),
        PrivateAccountRule(),
        FollowersOnlyPostRule(),
    ]
```

## `app/request/feed/types.py`（`FeedQuery` に 2 フィールド）

```python
muted_user_ids: set[uuid.UUID] = field(default_factory=set)
muted_keywords: set[str] = field(default_factory=set)
```

## `app/request/feed/pipeline.py`（足す箇所）

`BlockedUserIdsQueryHydrator` の直後:

```python
class MutedUserIdsQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(select(Mute.muted_id).where(Mute.muter_id == query.viewer_id))
        query.muted_user_ids = {row[0] for row in result.all()}
        return query


class MutedKeywordsQueryHydrator(QueryHydrator):
    async def hydrate(self, db: AsyncSession, query: FeedQuery) -> FeedQuery:
        result = await db.execute(
            select(MutedKeyword.keyword).where(MutedKeyword.user_id == query.viewer_id)
        )
        query.muted_keywords = {row[0] for row in result.all()}
        return query
```

`PolicyContext(...)` に `muted_user_ids=query.muted_user_ids` と `muted_keywords=query.muted_keywords` を渡す。

`build_feed_pipeline()` の hydrator リスト:

```python
FollowingQueryHydrator(),
BlockedUserIdsQueryHydrator(),
MutedUserIdsQueryHydrator(),
MutedKeywordsQueryHydrator(),
SeenPostsQueryHydrator(),
ViewerInterestQueryHydrator(),
```

import に `Mute` と `MutedKeyword` を足す。

## `ranking/weights.yaml`（差し替え・全文）

```yaml
recency: 0.30
in_network_boost: 0.25
engagement: 0.15
author_affinity: 0.10
similarity: 0.20
seen_penalty: -0.30
author_diversity_decay: 0.50
author_diversity_floor: 0.25
```

## `app/ranking/scorer.py`（`rank_candidates` 周り）

```python
def apply_author_diversity(
    candidates: list[FeedCandidate],
    *,
    decay: float,
    floor: float,
) -> list[FeedCandidate]:
    seen_count: dict[UUID, int] = {}
    for candidate in candidates:
        count = seen_count.get(candidate.author_id, 0)
        factor = max(floor, decay**count)
        if candidate.rank_score is not None:
            candidate.rank_score *= factor
        seen_count[candidate.author_id] = count + 1
    return sorted(candidates, key=lambda c: c.rank_score or 0.0, reverse=True)


def rank_candidates(...):
    for candidate in candidates:
        candidate.rank_score = score_candidate(query, candidate, weights, now=now)
    ordered = sorted(candidates, key=lambda c: c.rank_score or 0.0, reverse=True)
    return apply_author_diversity(
        ordered,
        decay=weights.author_diversity_decay,
        floor=weights.author_diversity_floor,
    )
```

`RankingWeights` と `load_weights()` に `author_diversity_decay` / `author_diversity_floor` を必須キーとして足す。

## `app/main.py`

- `version="1.1.0"`
- `mutes.router` と `muted_keywords.router` を include
- `/health` の version も `1.1.0`

テスト: `tests/test_mutes.py`, `tests/test_pre_score_filters.py`, `tests/test_ranking.py` の多様性ケース。全文はリポジトリを参照。

---

**シリーズ:** [第10回](10-out-of-network.md) ← **第11回** → [第12回](12-replies-threads.md)
