---
title: "個人開発 SNS を x-algorithm 流に設計する【第13回: 興味なし / 非表示編】"
series: sns-tutorial-x
part: 13
slug: sns-tutorial-x/13-not-interested
tags: [FastAPI, Policy, Ranking, feedback]
---

# 個人開発 SNS を x-algorithm 流に設計する【第13回: 興味なし / 非表示編】

この連載は **上から順にコピペする** と動くチュートリアルです。途中のコードは「今足す断片」、記事末尾が **この回の完成形** です。

**起点:** `git checkout v1.2`

## この回のゴール

- [ ] 非表示（hide）で **その投稿だけ** For You から落とす
- [ ] 興味なし（not_interested）でその投稿を落とし、**同じ作者の残りを Ranking で下げる**
- [ ] 作者には通知しない（いいねと逆）
- [ ] 負の重みを `weights.yaml` に明示する

**第13回終了時点のタグ:** `v1.3`

---

## 用語（この回で初登場）

### 負の行動 / negative action

x-algorithm の Phoenix は「いいねする確率」だけでなく、**興味なし・ミュート・ブロック・通報** の確率も出します。正の重みと負の重みを足して最終スコアにします。

本連載に Transformer はありません。代わりに、閲覧者が明示したフィードバックを:

| 層 | 問い | この回 |
|---|---|---|
| **Policy** | この投稿を見せるか？ | hide / not_interested の対象投稿は DROP |
| **Ranking** | 見せるなら何順か？ | not_interested した **作者** の他投稿に負の重み |

同じテーブルに書いても、**読む場所を分ける** のが第1回からの約束です。

### 非表示 vs 興味なし vs ミュート vs ブロック

| | その投稿 | その作者の他投稿 | フォロー |
|---|---|---|---|
| 非表示 `hide` | 出さない | そのまま | 維持 |
| 興味なし `not_interested` | 出さない | **下げる**（落とさない） | 維持 |
| ミュート | 出さない | 出さない | 維持 |
| ブロック | 出さない | 出さない | 切ることが多い |

興味なしは「この系統は少し要らない」で、ミュートは「この人は見えない」。

### 作者には知らせない

いいねは Request Path で通知します。負のフィードバックは **閲覧者の私的な設定** です。作者に送ると報復や萎縮が起きます。Labeling Path も使いません。Mute と同じく、書いた瞬間に次の `GET /feed` が読めば足ります。

### スレッドではまだ見える

For You から消えても `GET /posts/{id}` やスレッドでは読めます。x-algorithm の PreviouslySeen が「タイムラインに出さない」であって投稿そのものを消さないのと同じです。`thread_policy()` には `HiddenPostRule` を足しません。

---

## Step 1: `post_feedback`

`(viewer_id, post_id)` で 1 行。`kind` は `hide` か `not_interested`。同じ投稿に二度送ったら kind を上書きします。

API:

| メソッド | パス | 意味 |
|---|---|---|
| `POST` | `/feedback/{post_id}` | `{"kind": "hide"}` または `{"kind": "not_interested"}` |
| `GET` | `/feedback` | 自分の一覧 |
| `DELETE` | `/feedback/{post_id}` | 取り消し（TL に戻る） |

自分の投稿には送れません。

Alembic は `009`。

---

## Step 2: Policy — その投稿を落とす

`FeedbackQueryHydrator` が viewer の全フィードバックを読み、`hidden_post_ids` に **両方の kind** を入れます。`HiddenPostRule` は id が集合にあれば DROP。

---

## Step 3: Ranking — 作者を下げる

同じ Hydrator が `kind == not_interested` の投稿の **作者 id** を `not_interested_author_ids` に集めます。

```yaml
seen_penalty: -0.30
not_interested_author: -0.40
```

`seen_penalty` は「もう見た」。`not_interested_author` は「この作者は要らない傾向」。どちらも YAML の負数で、コードに `-0.4` を直書きしません。

```
score += w_not_interested_author * (1 if author in not_interested_author_ids else 0)
```

hide だけの作者はここに入りません。残りの投稿の順位は変わりません。

---

## Step 4: 接続

`build_feed_pipeline()` の QueryHydrator に `FeedbackQueryHydrator`。`PolicyContext` に `hidden_post_ids`。version `1.3.0`。

```bash
pip install -e ".[dev]"
pytest
```

---

# 第13回 完成形

## `app/core/social_models.py` に追加

```python
class FeedbackKind(str, enum.Enum):
    HIDE = "hide"
    NOT_INTERESTED = "not_interested"


class PostFeedback(Base):
    """Viewer-private negative signal. Never notified to the author."""

    __tablename__ = "post_feedback"
    __table_args__ = (UniqueConstraint("viewer_id", "post_id", name="uq_post_feedback_pair"),)

    viewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("posts.id"), primary_key=True
    )
    kind: Mapped[FeedbackKind] = mapped_column(
        Enum(FeedbackKind, name="feedback_kind", native_enum=False)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

`sqlalchemy` の import に `Enum` と、ファイル先頭に `import enum` が必要です。

## `alembic/versions/009_add_post_feedback.py`

```python
"""add post_feedback for hide and not-interested

Revision ID: 009
Revises: 008
Create Date: 2026-08-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "post_feedback",
        sa.Column("viewer_id", sa.UUID(), nullable=False),
        sa.Column("post_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"]),
        sa.ForeignKeyConstraint(["viewer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("viewer_id", "post_id"),
        sa.UniqueConstraint("viewer_id", "post_id", name="uq_post_feedback_pair"),
    )
    op.create_index("ix_post_feedback_post_id", "post_feedback", ["post_id"])


def downgrade() -> None:
    op.drop_index("ix_post_feedback_post_id", table_name="post_feedback")
    op.drop_table("post_feedback")
```

## `app/request/schemas.py` に追加

```python
class FeedbackCreateRequest(BaseModel):
    kind: str = Field(pattern="^(hide|not_interested)$")


class FeedbackResponse(BaseModel):
    viewer_id: uuid.UUID
    post_id: uuid.UUID
    kind: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

## `app/request/routers/feedback.py`（新規・全文）

リポジトリの同ファイルをコピーしてください。要点: 自分の投稿は 400。既存行があれば `kind` を上書き。通知は作らない。

## Policy / Ranking の断片

`PolicyContext.hidden_post_ids`。`HiddenPostRule` を `home_feed_policy()` の先頭へ。

```python
class HiddenPostRule(Rule):
    name = "HiddenPostRule"

    def evaluate(self, context: PolicyContext) -> PolicyVerdict:
        if context.candidate.id in context.hidden_post_ids:
            return PolicyVerdict.DROP
        return PolicyVerdict.ALLOW
```

`FeedQuery` に `hidden_post_ids` と `not_interested_author_ids`。

```python
class FeedbackQueryHydrator(QueryHydrator):
    async def hydrate(self, db, query):
        # 全 kind の post_id → hidden_post_ids
        # kind == not_interested の author_id → not_interested_author_ids
        ...
```

`score_candidate` に:

```python
+ weights.not_interested_author * (
    1.0 if candidate.author_id in query.not_interested_author_ids else 0.0
)
```

`ranking/weights.yaml`:

```yaml
seen_penalty: -0.30
not_interested_author: -0.40
```

`RankingWeights` と `load_weights()` の必須キーに `not_interested_author` を足す（fail-fast）。

`main.py` で `feedback.router` を include。version `1.3.0`。

テスト: `tests/test_feedback.py`、`tests/test_ranking.py` の作者減点。全文は `git checkout v1.3`。

---

**シリーズ:** [第12回](12-replies-threads.md) ← **第13回**
