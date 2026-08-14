---
title: "個人開発 SNS を x-algorithm 流に設計する【第1回: アーキテクチャ編】"
series: sns-tutorial-x
part: 1
slug: sns-tutorial-x/01-architecture
tags: [FastAPI, SNS, アーキテクチャ, x-algorithm]
---

# 個人開発 SNS を x-algorithm 流に設計する【第1回: アーキテクチャ編】

この連載は **上から順にコピペする** と動くチュートリアルです。途中のコードは「今足す断片」、記事末尾が **この回の完成形（コピペで動く）** です。

## この回のゴール

- [ ] x-algorithm から個人開発に持ち込める設計原則を理解する
- [ ] `sns-tutorial-x` の骨格を作る
- [ ] Docker Compose で API / PostgreSQL / Redis を起動する
- [ ] `GET /health` が `{"status":"ok","version":"0.1.0"}` を返す

**第1回終了時点のタグ:** `v0.1`

---

## 用語（この回で初登場）

### x-algorithm

X（旧 Twitter）が公開した **For You タイムライン** のオープンソース実装です。巨大な Rust サービス群なので、コードをコピーするのではなく **設計思想** だけ借ります。

参考: [xai-org/x-algorithm](https://github.com/xai-org/x-algorithm)

### FastAPI

Python の Web フレームワークです。関数に型を書くと、HTTP API と **OpenAPI**（後述）が自動でできます。同期処理も非同期処理（`async def`）も書けます。

### OpenAPI / `/docs`

API の仕様を機械可読にした規格です。FastAPI は起動すると `http://localhost:8000/docs` に Swagger UI を出します。ブラウザからエンドポイントを試せます。

### PostgreSQL

リレーショナルデータベース（表形式でデータを保存する DB）です。ユーザー・投稿・フォロー関係をここに置きます。第1回ではコンテナを起動するだけで、テーブルは第2回です。

### Redis

メモリ上の高速ストアです。本連載では第6回から **Redis Streams**（メッセージキュー）として使い、投稿後処理を Worker に渡します。第1回では箱だけ用意します。

### Docker / Docker Compose

アプリケーションと依存サービスをコンテナ（隔離されたプロセス）で動かす仕組みです。

- **Dockerfile:** 1 つのイメージ（API 用 Python 環境）の作り方
- **docker-compose.yml:** 複数コンテナ（api / postgres / redis）をまとめて起動する定義

### uvicorn

FastAPI アプリを HTTP サーバとして動かす **ASGI サーバ** です。ASGI は「非同期 Web アプリの接続規約」で、uvicorn がその実装の一つです。

### pydantic-settings

環境変数や `.env` ファイルを、型付きの設定クラスに読み込むライブラリです。`POSTGRES_HOST=postgres` のような値を `settings.postgres_host` で参照できます。

### structlog

ログを JSON などの構造化データとして出すライブラリです。あとから `request_id` などの文脈を足しやすいので、第8回の観測性につながります。

### pytest / httpx

- **pytest:** Python のテストランナー
- **httpx:** HTTP クライアント。テストでは本物のネットワークを使わず、FastAPI アプリに直接リクエストします（`ASGITransport`）

### Request Path / Labeling Path

x-algorithm の大きな切り分けです。

| 経路 | 誰が待つか | 例 |
|---|---|---|
| **Request Path** | ユーザー（ブラウザ / curl） | `GET /feed` |
| **Labeling Path** | 誰も待たない（裏方） | 投稿の公開、embedding、fan-out |

個人開発でよくある失敗は、タイムライン表示のたびに重い処理まで全部やることです。

```
❌ GET /feed の中で embedding 計算 → 遅い・壊れやすい
✅ POST /posts → 202 Accepted → Worker が裏で処理 → GET /feed は結果だけ読む
```

### Policy ≠ Ranking ≠ Labeling

| 層 | 問い | 例 |
|---|---|---|
| **Policy** | 見せるか？ | ブロック、非公開、凍結 |
| **Ranking** | 見せるなら何順？ | 新着、いいね数、フォロー中優先 |
| **Labeling** | 裏方で何を計算？ | embedding、通知、fan-out |

1 つの関数に `if blocked` と `score *= 0.8` を混ぜない、というのがこの連載の約束です。

### fail-fast / degrade

- **fail-fast（起動時）:** 設定ミスや DB 不通なら、壊れたまま動かさず起動を拒否する
- **degrade（実行時）:** 任意の付加処理が失敗しても、本体のレスポンスは返す

第1回は起動ログだけ。DB 接続チェックは第2回です。

### Git タグ

コミットに名前を付ける印です。`v0.1` をチェックアウトすると、第1回終了時点のコードに戻れます。

---

## 前提

| 項目 | 内容 |
|---|---|
| 想定読者 | バックエンド経験 1〜3 年 |
| 必要環境 | Docker Desktop、Git、Python 3.12+ |
| 前回までの状態 | なし（新規） |

---

## Step 1: リポジトリを作る

```bash
mkdir sns-tutorial-x
cd sns-tutorial-x
git init
```

`.gitignore` を置きます。Python のキャッシュ、仮想環境、秘密情報の `.env` を Git に入れないための一覧です。

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
.env
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.coverage
htmlcov/
```

---

## Step 2: Python プロジェクト定義

`pyproject.toml` は「このプロジェクトの名前・バージョン・依存ライブラリ」を書く標準ファイルです。`pip install -e ".[dev]"` すると、`app` パッケージを編集可能な状態でインストールできます。

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[project]
name = "sns-tutorial-x"
version = "0.1.0"
description = "Copy-paste SNS backend tutorial inspired by x-algorithm design patterns"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic-settings>=2.6.0",
    "structlog>=24.4.0",
]

[project.optional-dependencies]
dev = [
    "httpx>=0.28.0",
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

**hatchling** はパッケージをビルドするツールです。`packages = ["app"]` で `app/` ディレクトリをインストール対象にします。

ローカルで動かす場合:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

---

## Step 3: パッケージの空箱

Python はディレクトリに `__init__.py` があるとパッケージとして import できます。中身は空で構いません。

```
app/
  __init__.py
  core/__init__.py      # 設定など横断（ビジネスロジックは書かない）
  request/__init__.py   # Request Path（第2回〜）
  labeling/__init__.py  # Labeling Path（第6回〜）
  policy/__init__.py    # 見せる/見せない（第4回〜）
  ranking/__init__.py   # 順序付け（第5回〜）
```

空ファイルを 6 つ作ってください（記事末尾の完成形に全文があります）。

**ポイント:** `core/` に機能コードを書かない。機能追加は `request/` か `labeling/` に閉じます。x-algorithm の grox が `core/` と `flows/` を分けているのと同じ発想です。

---

## Step 4: 設定クラス

`app/core/config.py` を作ります。環境変数名は大文字（`APP_ENV`）でも、フィールドは小文字（`app_env`）で読めます。pydantic-settings が変換します。

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "sns"
    postgres_password: str = "sns"
    postgres_db: str = "sns"

    redis_host: str = "localhost"
    redis_port: int = 6379
```

続けて、接続文字列をプロパティで組み立てます。第2回の SQLAlchemy がこれを使います。

```python
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
```

`extra="ignore"` は、まだ使わない環境変数があってもエラーにしない設定です。第2回で JWT 用の変数を足しても、第1回のコードはそのまま動きます。

`.env.example` を置き、コピーして `.env` にします。

```bash
cp .env.example .env
```

Docker 内では Postgres のホスト名が `localhost` ではなくサービス名 `postgres` になります。`.env.example` はその前提で書いてあります。

---

## Step 5: FastAPI エントリポイント

`app/main.py` を作ります。まずアプリとヘルスチェックだけ。

```python
from fastapi import FastAPI

app = FastAPI(
    title="sns-tutorial-x",
    description="Personal SNS API tutorial (x-algorithm inspired, copy-paste edition)",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
```

**lifespan** はアプリ起動・終了時に走るフックです。ここにログ設定を置きます。

```python
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import settings

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
    yield
    logger.info("shutdown")


app = FastAPI(
    title="sns-tutorial-x",
    description="Personal SNS API tutorial (x-algorithm inspired, copy-paste edition)",
    version="0.1.0",
    lifespan=lifespan,
)
```

`yield` の前が起動処理、後が終了処理です。第2回で `yield` の前に Postgres 接続チェックを足します。

ローカル確認（Docker なし）:

```bash
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

---

## Step 6: Docker Compose

3 サービスを並べます。

| サービス | 役割 |
|---|---|
| `api` | FastAPI |
| `postgres` | 本体 DB（第2回〜使用） |
| `redis` | キュー（第6回〜使用） |

`healthcheck` は「準備ができるまで api を待たせる」ための検査です。`depends_on` の `condition: service_healthy` と組み合わせます。

`Dockerfile` は API イメージです。`CMD` で uvicorn を起動します。

`docker-compose.yml` の `command` で `--reload` を上書きしているので、開発中は `app/` を編集すると API が再起動します。

```bash
docker compose up --build
```

別ターミナル:

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

OpenAPI UI: http://localhost:8000/docs

---

## Step 7: テスト

`tests/test_health.py` です。`ASGITransport` は「本物の TCP ポートを開けずに FastAPI アプリへ HTTP 相当の呼び出しをする」仕組みです。

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
```

```bash
pytest
```

1 件成功すれば第1回のコードは完成です。

---

## この回であえて作らないもの

| 機能 | 登場回 |
|---|---|
| users / posts テーブル | 第2回 |
| JWT 認証 | 第2回 |
| `/feed` | 第3回 |
| Policy / Ranking | 第4〜5回 |
| Worker / Redis Streams | 第6回 |

空の `/health` に見えても、**ディレクトリと原則が第10回まで使い回せる** のが成果です。

---

## よくある失敗

1. **最初から全部入れる** — 認証・TL・通知を第1回に入れると設計の学びが埋もれます。
2. **Policy と Ranking を 1 関数に書く** — 第4〜5回で分離します。
3. **Labeling を Request Path に混ぜる** — 投稿 API で同期 fan-out するとフォロワー増加で `POST /posts` が落ちます。
4. **core/ に機能コードを書く** — 機能は `request/` か `labeling/` へ。

---

## チェックリスト

- [ ] ディレクトリ構成（`core`, `request`, `labeling`, `policy`, `ranking`）
- [ ] `docker compose up` で 3 サービス起動
- [ ] `curl /health` → `{"status":"ok","version":"0.1.0"}`
- [ ] `pytest` 成功

---

## 次回予告

**第2回: API & DB & 認証** — `users` / `posts` / `follows`、bcrypt + JWT、起動時 Postgres fail-fast。

---

# 第1回 完成形（コピペで動く）

以下をリポジトリルートに配置してください。空の `__init__.py` は中身なしで作成します。

### `.gitignore`

```
__pycache__/
*.py[cod]
.venv/
venv/
.env
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.coverage
htmlcov/
```

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[project]
name = "sns-tutorial-x"
version = "0.1.0"
description = "Copy-paste SNS backend tutorial inspired by x-algorithm design patterns"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic-settings>=2.6.0",
    "structlog>=24.4.0",
]

[project.optional-dependencies]
dev = [
    "httpx>=0.28.0",
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

### `.env.example`

```
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=info

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=sns
POSTGRES_PASSWORD=sns
POSTGRES_DB=sns

REDIS_HOST=redis
REDIS_PORT=6379
```

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `docker-compose.yml`

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app:ro
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: sns
      POSTGRES_PASSWORD: sns
      POSTGRES_DB: sns
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sns -d sns"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
```

### `app/core/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "info"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "sns"
    postgres_password: str = "sns"
    postgres_db: str = "sns"

    redis_host: str = "localhost"
    redis_port: int = 6379

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
```

### `app/main.py`

```python
import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import settings

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
    yield
    logger.info("shutdown")


app = FastAPI(
    title="sns-tutorial-x",
    description="Personal SNS API tutorial (x-algorithm inspired, copy-paste edition)",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
```

### `tests/test_health.py`

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
```

空ファイル: `app/__init__.py`, `app/core/__init__.py`, `app/request/__init__.py`, `app/labeling/__init__.py`, `app/policy/__init__.py`, `app/ranking/__init__.py`

README はリポジトリ直下の `README.md` を使ってください。

動作確認:

```bash
cp .env.example .env
pip install -e ".[dev]"
pytest
```

---

**シリーズ:** **第1回** → 第2回: API & DB & 認証
