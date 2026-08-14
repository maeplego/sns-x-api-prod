---
title: "個人開発 SNS を x-algorithm 流に設計する【第15回: Who to Follow 編】"
series: sns-tutorial-x
part: 15
slug: sns-tutorial-x/15-who-to-follow
tags: [FastAPI, feed, blender, Who to Follow]
---

# 個人開発 SNS を x-algorithm 流に設計する【第15回: Who to Follow 編】

この連載は **上から順にコピペする** と動くチュートリアルです。途中のコードは「今足す断片」、記事末尾が **この回の完成形** です。

**起点:** `git checkout v1.4`

## この回のゴール

- [ ] 投稿以外のアイテムを TL の **固定位置** に差し込む（Blending Pipeline）
- [ ] 候補は **共通のフォロー**（friends-of-friends）。学習済み推薦モデルは使わない
- [ ] すでにフォローしている人、自分、ブロック、ミュート、非公開、停止アカウントは出さない
- [ ] `GET /who-to-follow` でも同じリストを返せる

**第15回終了時点のタグ:** `v1.5`

---

## 用語（この回で初登場）

### Blending Pipeline

第10回の `SourceBlender` は **投稿ソース同士**（Thunder と OON）を混ぜます。x-algorithm の Blending Pipeline は、そのあと **投稿ではないもの** を差し込みます。広告、Who to Follow、プロンプトです。

本連載は広告をやりません。Who to Follow だけを、本家と同じ **6 番目のスロット** に置きます。ページが 6 本未満なら末尾です。

```
Post Pipeline（第3〜14回）
    Thunder / OON → Policy → Ranker → ページ切る
            ↓
Blending Pipeline（この回）
    ランク済み投稿の 6 番目に Who to Follow モジュール
```

並べ直しません。投稿の順位は Post Pipeline が決めたままです。モジュールは「この位置に出す」だけです。

### Who to Follow / フォローする人

TL の途中に出る「この人をフォローしませんか」カードです。本家は別サービス（Account Recommendations Mixer）に問い合わせ、最大 3 人です。こちらは SQL 1 本で同じ形にします。

### Friends-of-friends / 共通のフォロー

Alice が Bob と Dana をフォローしていて、二人が Carol をフォローしているなら、Carol は Alice の **2-hop** です。共通のフォロー数が多い人を先に出します。

Phoenix も SimClusters も使いません。「同じ人を追っている」はグラフの隣接だけで足ります。

### `kind` でアイテムを分ける

これまで `items` は投稿だけでした。モジュールを混ぜると、クライアントは `body` があるとは限りません。各要素に `kind` を付けます。

| kind | 中身 |
|---|---|
| `post` | 今までの投稿 |
| `who_to_follow` | おすすめユーザーの配列（最大 3） |

インプレッション（「見せた投稿」）は `kind == post` だけ数えます。

---

## 前提

| 項目 | 内容 |
|---|---|
| 起点 | `v1.4` |
| 触る層 | Request Path の Blender とフィード API |
| 触らない層 | Labeling Path、DB スキーマ、広告 |

新しいテーブルはありません。フォローグラフをリクエストのたびに読みます。

本家の Following 面は投稿が 10 本を超えるまで Who to Follow を出しません。個人 SNS では TL が短いので、**候補があるなら出す** にします。2 ページ目（`cursor` あり）には出しません。疲労テーブルの縮小版です。

---

## Step 1: レスポンスを union にする

`FeedPostItem` に `kind: "post"`。Who to Follow 用の型を足します。

```python
class WhoToFollowUserItem(BaseModel):
    id: uuid.UUID
    handle: str
    display_name: str
    mutual_follow_count: int
    reason: str = "mutual_follows"


class WhoToFollowModuleItem(BaseModel):
    kind: Literal["who_to_follow"] = "who_to_follow"
    users: list[WhoToFollowUserItem]
```

`FeedResponse.items` は `post | who_to_follow` の discriminated union（`kind` でどちらと決める）です。

---

## Step 2: 共通フォローを取る

`app/request/feed/who_to_follow.py`:

1. 閲覧者がフォローしている ID を取る
2. その人たちがフォローしている人を数え、閲覧者・既存フォロー・ブロック双方・ミュートを除く
3. `active` かつ非公開でないユーザーだけ残す
4. 共通数の多い順、最大 3 人

```python
select(Follow.followee_id, func.count())
.where(
    Follow.follower_id.in_(following_ids),
    Follow.followee_id.notin_(excluded),
)
.group_by(Follow.followee_id)
```

`reason` は今は `mutual_follows` だけです。あとから「同じ投稿にいいねした」を足しても、モジュールの形は変わりません。

---

## Step 3: 固定位置に差し込む

`SourceBlender` の隣に `insert_who_to_follow`。定数 `WHO_TO_FOLLOW_POSITION = 6` は home-mixer と同じ 1-indexed です。

```python
insert_idx = min(WHO_TO_FOLLOW_POSITION - 1, len(items))
result.insert(insert_idx, module)
```

Post Pipeline のあとに呼びます。`cursor` が無いときだけ。`GET /who-to-follow` は差し込みなしで同じ `fetch_who_to_follow` を返します。

version は `1.5.0`。

```bash
pip install -e ".[dev]"
pytest
```

---

# 第15回 完成形

以下はこの回で新規または差し替えるファイルです。`router.py` の全体は `git checkout v1.5`。

## `app/request/feed/blender.py` に追加

```python
WHO_TO_FOLLOW_POSITION = 6


def insert_who_to_follow(items: list, module) -> list:
    result = list(items)
    insert_idx = min(WHO_TO_FOLLOW_POSITION - 1, len(result))
    result.insert(insert_idx, module)
    return result
```

## `app/request/feed/who_to_follow.py`（新規）

```python
MAX_WHO_TO_FOLLOW_USERS = 3
FOF_FETCH_LIMIT = 20


async def fetch_who_to_follow(db, viewer_id, limit=MAX_WHO_TO_FOLLOW_USERS):
    # following_ids が空なら []
    # excluded = following ∪ {viewer} ∪ blocks ∪ blocked-by ∪ mutes
    # FoF を count desc で取り、active かつ not private を limit 人
    ...
```

全文はタグ `v1.5`。

## `app/request/feed/schemas.py`

`FeedPostItem.kind`、`WhoToFollowUserItem`、`WhoToFollowModuleItem`、`WhoToFollowResponse`。`FeedResponse.items` を union に。

## ルータ断片

```python
items = _post_items(candidates)
if cursor is None:
    users = await fetch_who_to_follow(db, current_user.id)
    if users:
        items = insert_who_to_follow(items, WhoToFollowModuleItem(users=users))

background_tasks.add_task(..., [item.id for item in items if item.kind == "post"])
```

`GET /who-to-follow` を同じルータに足す。For You と Following の両方に差し込む。

`main.py` / `/health` / `pyproject.toml` の version は `1.5.0`。

テスト: `tests/test_who_to_follow.py`、`tests/test_blender.py` の差し込み位置。既存の TL テストは 2-hop が無いのでモジュールは出ません。全文は `git checkout v1.5`。

---

**シリーズ:** [第14回](14-following-timeline.md) ← **第15回** → [まとめ](16-series-map.md)
