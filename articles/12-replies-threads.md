---
title: "個人開発 SNS を x-algorithm 流に設計する【第12回: 返信 / スレッド編】"
series: sns-tutorial-x
part: 12
slug: sns-tutorial-x/12-replies-threads
tags: [FastAPI, Policy, threads, replies]
---

# 個人開発 SNS を x-algorithm 流に設計する【第12回: 返信 / スレッド編】

この連載は **上から順にコピペする** と動くチュートリアルです。途中のコードは「今足す断片」、記事末尾が **この回の完成形** です。

**起点:** `git checkout v1.1`

## この回のゴール

- [ ] 投稿に `parent_id` / `root_id` を足し、返信を作れる
- [ ] `GET /posts/{id}/thread` で会話を時系列に返す
- [ ] 親の `reply_count` と通知を Labeling Path で更新する
- [ ] For You では会話を 1 件に畳む（`DedupConversationFilter`）
- [ ] 親が見えない返信は DROP する（`AncillaryVF` の縮小版）

**第12回終了時点のタグ:** `v1.2`

---

## 用語（この回で初登場）

### スレッド / 会話（conversation）

1 本の元投稿と、それにぶら下がる返信の集まりです。返信の返信も同じ会話です。

- **parent_id:** 直近の親
- **root_id:** 会話の頂点（元投稿の id）。ネストしても根は変わらない

`root_id` を持たないと、フィードで「同じ会話か」を毎回再帰することになります。書く時点で根を確定します。

### AncillaryVF / `ReplyAncillaryRule`

x-algorithm は Visibility Filtering のあと、**親・引用元が DROP なら子も DROP** します。フォロー中の人が、ブロックした人の投稿に返信しても、その返信は出ません。

### DedupConversationFilter

同じ会話から For You に複数本載せないフィルタです。本連載の規則:

1. **根が候補にいる** → 根を残し、返信は落とす
2. **根がいない**（フォローしていない人への返信だけが見える）→ その会話からスコア最大の返信を 1 本

スレッド画面は別 API なので、ここで畳んでも会話は失われません。

### OON に返信を載せない

x-algorithm の `OONRetweetReplyFilter` に相当します。おすすめ検索は **元投稿だけ**。返信は Thunder（フォロー中）経由だけ候補になります。

### 可視性の継承

返信の `visibility` は親の値をコピーします。フォロワー限定の投稿への公開返信で中身が漏れるのを防ぎます。

---

## 前提

| 項目 | 内容 |
|---|---|
| 起点 | `v1.1` |
| 触る層 | モデル、Labeling（新 Plan）、Policy、パイプラインの Hydrator / Deduper |

Plan 順:

```
publish(0) → embedding(25) → fanout(50) → reply_side_effects(75) → engagement_init(100)
```

---

## Step 1: スキーマと API

`posts` に `parent_id` / `root_id`（nullable FK）。Alembic `008`。

`POST /posts` に任意の `parent_id`:

- 親が published で未削除であること
- ブロック関係・非公開・フォロワー限定なら 403
- `visibility` は親から継承
- `root_id = parent.root_id or parent.id`

`GET /posts/{id}/thread` は同じ `root_id` の投稿を集め、thread 用 Policy（Self / Age なし）を通したあと、親が見えない子を落とします。プロフィール `GET /users/{handle}/posts` は **元投稿だけ**（`parent_id IS NULL`）。

---

## Step 2: Labeling — `reply_side_effects`

返信も `post.created` です。新しい Plan を足すだけで、publish / fan-out は既存のまま動きます。

- `IncrementReplyCountTask` — 親への published 返信を **数え直す**（インクリメントだと Worker 再実行でズレる）
- `NotifyReplyTask` — 親の作者へ `post_replied`（自分への返信は送らない）

`app/labeling/flows/reply/` には **`__init__.py` が必要** です。`pkgutil.iter_modules` はそれがないサブディレクトリを Plan として拾いません。

---

## Step 3: Policy と Hydrator

`ParentHydrator` が返信の親作者・可視性を載せる。そのあと:

- `OonReplyRule` — `source == "oon"` の返信を DROP
- `ReplyAncillaryRule` — 親が欠ける / ブロック / ミュート / 非公開なら DROP

OON 検索自体も `parent_id IS NULL` にします。Viewer の興味ベクトルは **元投稿の embedding だけ** から作ります（返信本文で親がおすすめに浮上して畳み込みが崩れるのを避ける）。

---

## Step 4: 会話の畳み込み

Ranking のあと、Selector の前:

```python
def dedupe_conversations(candidates):
    conversations_with_root = {c.root_id or c.id for c in candidates if c.parent_id is None}
    ...
```

根がある会話の返信はページから消えます。クライアントは `parent_id` 付きの孤立返信だけ「返信です」と描きます。

```bash
pip install -e ".[dev]"
pytest
```

---

# 第12回 完成形

新規ファイルの全文と、既存ファイルへの差し込みです。`pipeline.py` の全体は `git checkout v1.2`。

## `alembic/versions/008_add_post_threads.py`

```python
"""add post parent_id and root_id for threads

Revision ID: 008
Revises: 007
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("posts", sa.Column("parent_id", sa.UUID(), nullable=True))
    op.add_column("posts", sa.Column("root_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_posts_parent_id", "posts", "posts", ["parent_id"], ["id"])
    op.create_foreign_key("fk_posts_root_id", "posts", "posts", ["root_id"], ["id"])
    op.create_index("ix_posts_parent_id", "posts", ["parent_id"])
    op.create_index("ix_posts_root_id", "posts", ["root_id"])


def downgrade() -> None:
    op.drop_index("ix_posts_root_id", table_name="posts")
    op.drop_index("ix_posts_parent_id", table_name="posts")
    op.drop_constraint("fk_posts_root_id", "posts", type_="foreignkey")
    op.drop_constraint("fk_posts_parent_id", "posts", type_="foreignkey")
    op.drop_column("posts", "root_id")
    op.drop_column("posts", "parent_id")
```

## `Post` モデルに追加

```python
parent_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("posts.id"), nullable=True, index=True
)
root_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("posts.id"), nullable=True, index=True
)
```

## `app/labeling/flows/reply/__init__.py`

空ファイルでよい。**置かないと Plan が登録されない。**

## `app/labeling/flows/reply/plan.py`

```python
from app.core.registry import register
from app.labeling.events import POST_CREATED
from app.labeling.flows.reply.tasks import IncrementReplyCountTask, NotifyReplyTask
from app.labeling.plan import run_plan
from app.labeling.registry import Plan


@register
class ReplySideEffectsPlan(Plan):
    KEY = "reply_side_effects"
    EVENT_TYPES = [POST_CREATED]
    ORDER = 75

    TASKS = {
        "reply_count": IncrementReplyCountTask,
        "notify": NotifyReplyTask,
    }

    TASK_DEPENDENCIES = {
        "reply_count": set(),
        "notify": set(),
    }

    async def execute(self, ctx) -> bool:
        return await run_plan(self.TASKS, self.TASK_DEPENDENCIES, ctx)
```

## `app/labeling/flows/reply/tasks.py`

全文はリポジトリの同パス。要点:

- 親への published 返信を `COUNT` して `PostEngagement.reply_count` に書く
- `payload_json["reply_id"]` で通知の冪等性を取る

## Policy に追加する Rule

```python
class OonReplyRule(Rule):
    name = "OonReplyRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        candidate = context.candidate
        if candidate.parent_id is None:
            return PolicyVerdict.ALLOW
        if candidate.source == "oon":
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW


class ReplyAncillaryRule(Rule):
    name = "ReplyAncillaryRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        candidate = context.candidate
        if candidate.parent_id is None:
            return PolicyVerdict.ALLOW
        if candidate.parent_missing or candidate.parent_author_id is None:
            return PolicyVerdict.DROP
        parent_author_id = candidate.parent_author_id
        if parent_author_id in context.blocked_user_ids:
            return PolicyVerdict.DROP
        if parent_author_id in context.muted_user_ids:
            return PolicyVerdict.DROP
        # 親が suspended / private / followers_only なら同様に DROP
        ...
```

`home_feed_policy()` の末尾に `OonReplyRule`, `ReplyAncillaryRule`。`thread_policy()` は Self / Age / OON なし（スレッドでは自分の投稿も古い投稿も見せる）。

## パイプライン断片

`FeedCandidate` に `parent_id`, `root_id`, `parent_missing`, `parent_author_id`, `parent_visibility`, `parent_author_is_private`, `parent_author_status`。

`ParentHydrator` を `AuthorHydrator` のあとへ。`rank_candidates` のあと `dedupe_conversations`。

OON 検索の WHERE に `Post.parent_id.is_(None)`。

`main.py` / `/health` / `pyproject.toml` の version は `1.2.0`。

テスト: `tests/test_threads.py`, `tests/test_conversation_dedupe.py`。registry の期待順に `reply_side_effects` を挟む。

---

**シリーズ:** [第11回](11-mutes-filters-diversity.md) ← **第12回** → [第13回](13-not-interested.md)
