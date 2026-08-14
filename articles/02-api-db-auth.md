---
title: "個人開発 SNS を x-algorithm 流に設計する【第2回: API & DB & 認証編】"
series: sns-tutorial-x
part: 2
slug: sns-tutorial-x/02-api-db-auth
tags: [FastAPI, PostgreSQL, Alembic, JWT]
---

# 個人開発 SNS を x-algorithm 流に設計する【第2回: API & DB & 認証編】

第1回の骨格に、ユーザー・投稿・フォローとログインを足します。タイムラインはまだありません。

**起点:** `git checkout v0.1`

## この回のゴール

- [ ] `users` / `posts` / `follows` テーブルを Alembic で作る
- [ ] signup / login（bcrypt + JWT）
- [ ] `POST /posts` で投稿できる（この回は同期で公開）
- [ ] 起動時に Postgres / Redis へ接続できなければ落とす（fail-fast）

**第2回終了時点のタグ:** `v0.2`

---

## 用語（この回で初登場）

### ORM / SQLAlchemy

**ORM（Object-Relational Mapping）** は、Python のクラスを DB の表に対応させる仕組みです。`User(handle="alice")` を書くと `INSERT INTO users ...` になります。

**SQLAlchemy** はその代表ライブラリです。本連載は非同期版（`asyncio`）を使い、`asyncpg` という Postgres ドライバで接続します。

### Alembic

SQLAlchemy 公式の **マイグレーション** ツールです。テーブル追加を「バージョン付きの Python ファイル」として残し、`alembic upgrade head` で本番 DB に適用します。手で `CREATE TABLE` すると環境差で壊れやすいので、最初から Alembic を使います。

### UUID

128 ビットの一意 ID です。連番 `1, 2, 3...` と違い、他の表と衝突しにくく、ID から件数も推測されません。

### bcrypt

パスワードを **ハッシュ**（不可逆な指紋）にして保存するアルゴリズムです。平文パスワードを DB に置かない、が原則です。

### JWT（JSON Web Token）

ログイン後にクライアントへ渡す短い署名付き文字列です。以降のリクエストは `Authorization: Bearer <token>` ヘッダで「誰か」を証明します。本連載の Phase 1 は JWT、パスキー（FIDO2）は対象外です。

### FastAPI の Depends（依存性注入）

関数の引数に `Depends(get_db)` と書くと、FastAPI が DB セッションを用意して渡します。`get_current_user` も同じ仕組みで「トークン → ユーザー」を共通化します。

### pytest fixture / StaticPool

**fixture** はテストの前準備です。`conftest.py` の `client` がメモリ上の SQLite を作り、各テストに HTTP クライアントを渡します。

**StaticPool** は「接続を 1 本だけ使い回す」設定です。SQLite の `:memory:` は接続ごとに別 DB になるため、これがないとテーブルが見えなくなります。

---

## Step 1: 依存ライブラリを足す

`pyproject.toml` の `dependencies` に追加します。

```toml
    "pydantic[email]>=2.10.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "bcrypt>=4.2.0",
    "pyjwt>=2.10.0",
    "redis>=5.2.0",
```

開発用に `aiosqlite` も足します（テストで Postgres を起動しないため）。

```bash
pip install -e ".[dev]"
```

`version` を `0.2.0` に上げます。

---

## Step 2: JWT 設定

`app/core/config.py` の Redis 設定の下に足します。

```python
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
```

`.env.example` にも:

```
JWT_SECRET=change-me-in-production
JWT_EXPIRE_HOURS=24
```

**HS256** は「共有秘密鍵で署名する」方式です。本番では長いランダム文字列にしてください。

---

## Step 3: モデル（表の Python 表現）

`app/core/models.py` を新規作成します。まず土台:

```python
class Base(DeclarativeBase):
    pass
```

すべての表クラスがこの `Base` を継承します。Alembic は `Base.metadata` を見て表一覧を知ります。

ユーザー:

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    handle: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # display_name, bio, is_private, status, created_at ...
```

投稿とフォローも同様です。フォローは `(follower_id, followee_id)` の複合主キーで「同じ人を二度フォローできない」ようにします。

完成形は記事末尾に全文があります。

---

## Step 4: DB セッション

`app/core/database.py` を新規作成します。

```python
engine = create_async_engine(settings.async_database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

`pool_pre_ping=True` は、切れた接続を使う前に ping して張り直す設定です。

---

## Step 5: 起動時 fail-fast

`app/core/startup.py` を新規作成します。

```python
async def verify_postgres() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

async def run_startup_checks() -> None:
    await verify_postgres()
    await verify_redis()
```

`app/main.py` の lifespan で、テスト以外のときだけ呼びます。

```python
    if settings.app_env != "test":
        await run_startup_checks()
```

テストは SQLite を使うので、本物の Postgres が無くても pytest が通るようにします。

---

## Step 6: 認証ヘルパー

`app/request/auth.py` を新規作成します。パスワード:

```python
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
```

JWT:

```python
def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
```

`sub`（subject）は JWT の慣例で「誰のトークンか」を表します。

`get_current_user` はヘッダが無い / 壊れている / 停止アカウントなら 401 または 403 を返します。

---

## Step 7: ルーター

`app/request/schemas.py` にリクエスト/レスポンスの型を置きます。Pydantic モデルです。API の入力検証と OpenAPI ドキュメントの両方に使われます。

ルーターは機能ごとにファイルを分けます。

| パス | 役割 |
|---|---|
| `POST /auth/signup` | 登録 |
| `POST /auth/login` | トークン発行 |
| `GET /users/me` | 自分のプロフィール |
| `POST /posts` | 投稿（この回は **201 + published**） |
| `POST /follows/{user_id}` | フォロー |

第6回で `POST /posts` は **202 + processing** に変わり、Worker が裏で公開します。今は Request Path だけで完結させます。

`app/main.py` にルーターを登録します。

```python
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(follows.router)
```

`/health` の version を `0.2.0` に更新します。

---

## Step 8: Alembic

```bash
# すでに alembic.ini / alembic/ を記事末尾からコピーした場合は不要
alembic upgrade head
```

Docker では起動コマンドを次のようにします。

```
alembic upgrade head && uvicorn app.main:app ...
```

これでコンテナ起動時に表が必ず最新になります。

---

## Step 9: テスト

`tests/conftest.py` が SQLite メモリ DB を作り、`get_db` を差し替えます。

```bash
pytest
```

期待: health 1 件 + API 2 件が成功。

curl 例:

```bash
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"handle":"alice","email":"alice@example.com","password":"password123","display_name":"Alice"}'

curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"password123"}'
```

返ってきた `access_token` を使って投稿します。

---

## チェックリスト

- [ ] signup → login → `/users/me`
- [ ] フォローと投稿ができる
- [ ] 未認証の `POST /posts` は 401
- [ ] `pytest` 成功

---

## 次回予告

**第3回: タイムラインパイプライン** — `GET /feed` を QueryHydrator → Source → Hydrator → Selector で組み立てます（Pull モデル）。

---

# 第2回 完成形（この回で新規・変更したファイル）

第1回のファイルに加えて、以下を配置します。変更ファイルは **全文置換** してください。

### 変更: `pyproject.toml`

`version = "0.2.0"`。dependencies に sqlalchemy / alembic / bcrypt / pyjwt / redis / pydantic[email] / asyncpg。dev に aiosqlite。

### 変更: `app/core/config.py`

JWT 3 フィールドを追加（記事 Step 2）。

### 変更: `app/main.py`

下記が完成形です。

```python
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import settings
from app.core.startup import run_startup_checks
from app.request.routers import auth, follows, posts, users

logger = structlog.get_logger(__name__)


def configure_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "startup",
        app_env=settings.app_env,
        postgres_host=settings.postgres_host,
        redis_host=settings.redis_host,
    )
    if settings.app_env != "test":
        await run_startup_checks()
    yield
    logger.info("shutdown")


app = FastAPI(
    title="sns-tutorial-x",
    description="Personal SNS API tutorial (x-algorithm inspired, copy-paste edition)",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(follows.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.2.0"}
```

### 新規: `app/core/models.py` / `database.py` / `startup.py`

リポジトリの同名ファイルをそのままコピーしてください（この回の Git タグ `v0.2` と一致します）。

### 新規: `app/request/auth.py` / `schemas.py` / `routers/*.py`

同様にリポジトリをコピーしてください。

### 新規: `alembic.ini` / `alembic/env.py` / `alembic/versions/001_initial_schema.py`

### 新規: `tests/conftest.py` / `tests/test_api.py`

### 変更: `tests/test_health.py`

期待バージョンを `0.2.0` に。

### 変更: `Dockerfile` / `docker-compose.yml`

起動前に `alembic upgrade head` を実行するよう更新。

動作確認:

```bash
pip install -e ".[dev]"
pytest
```

リポジトリをクローンしている場合は、各回の完成形はタグで取れます。

```bash
git checkout v0.2
```

記事中の断片で「今なにを足したか」を追い、詰まったらタグの完成形と差分を見てください。

---

**シリーズ:** [第1回](01-architecture.md) ← **第2回** → 第3回
