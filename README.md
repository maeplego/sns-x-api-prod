# sns-tutorial-x-api

[sns-tutorial-x](../sns-tutorial-x)（`v1.5`）の **プロダクト用フォーク** です。チュートリアル本体は凍結したまま、フロント（`sns-tutorial-x-frontend`）から叩く API をここに足します。

## 起動

```bash
cd sns-tutorial-x-api
cp .env.example .env
docker compose up --build
```

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"2.0.0"}
```

Vite 開発サーバ（`http://localhost:5173`）向けの CORS がデフォルトで開いています。`CORS_ORIGINS` で変更します。

## このフォークで足したもの

- CORS
- 公開プロフィールから email を外す（`GET /users/{handle}`）
- `PATCH /users/me`
- フォロワー / フォロー一覧と件数
- プロフィール投稿の cursor ページング
- `POST /notifications/read`
- フォロー時に過去投稿を `user_feed` へ埋め戻し（アンフォローで削除）
- Compose の Postgres / Redis 永続ボリューム

## テスト

```bash
pip install -e ".[dev]"
pytest
```
