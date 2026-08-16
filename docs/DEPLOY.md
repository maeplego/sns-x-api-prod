# Deploy runbook（AWS / Terraform）

個人開発規模で `sns-x-api-prod` + `sns-x-frontend-prod` を公開する手順です。構成の意図は [INFRASTRUCTURE.md](INFRASTRUCTURE.md)。

前提:

- AWS アカウント（請求アラーム設定済み）
- ドメイン（Route53 にホストゾーンがあるか、NS を向けられる）
- Terraform `>= 1.5`
- AWS CLI v2、Docker、Node 20+
- GitHub リポジトリへの push 権限（OIDC 用）

---

## 0. 公開前チェック（アプリ側）

[OPERATIONS.md](OPERATIONS.md) に加え:

- [ ] `docs/legal/*` と FE `src/legal/content.ts` を見直し（必要なら専門家レビュー）
- [ ] 連絡先: FE の `VITE_OPERATOR_NAME` / `VITE_CONTACT_EMAIL`
- [ ] ローカルで `docker compose -f docker-compose.prod.yml up --build` が通る
- [ ] `pytest` / FE `npm run build` / smoke E2E が通る

---

## 1. AWS 初期設定（手動・一度きり）

1. ルート以外の作業用 IAM ユーザーまたは IAM Identity Center ユーザーを用意する。
2. **請求アラーム**（例: $30 / $80）を CloudWatch で設定する。
3. リージョンは **`ap-northeast-1`** に固定する。
4. （任意）AWS Budgets で月次予算を設定する。

---

## 2. Terraform state の bootstrap

```bash
cd sns-x-api-prod/infra/bootstrap
cp terraform.tfvars.example terraform.tfvars
# project_name / aws_region を編集
terraform init
terraform apply
```

出力される `state_bucket` / `lock_table` を控える。

`envs/prod/backend.hcl.example` を `backend.hcl` にコピーし、バケット名などを埋める。

---

## 3. 本番インフラ apply（Phase 1）

```bash
cd sns-x-api-prod/infra/envs/prod
cp terraform.tfvars.example terraform.tfvars
# domain_name, alert_email などを編集
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

主な成果物（output）:

| Output | 用途 |
|---|---|
| `ecr_repository_url` | API イメージ push 先 |
| `alb_dns_name` | API の一時確認 URL |
| `cloudfront_domain_name` | FE の一時確認 URL |
| `frontend_bucket` | `aws s3 sync` 先 |
| `rds_endpoint` / `redis_endpoint` | アプリ環境変数 |

初回 apply 後:

1. ACM 証明書の **DNS 検証レコード** を Route53 に入れる（モジュールが自動作成する想定ならスキップ）。
2. ホストゾーンの NS がレジストラに設定されていることを確認する。

### Phase 0 のみで始める場合

`infra/` の Lightsail/EC2 用コメントに従うか、手作業で:

1. Lightsail / EC2 を起動（Ubuntu 22.04 + Docker）。
2. セキュリティグループで 80/443 のみ開放。
3. リポジトリを clone し `.env` を本番値で作成。
4. `docker compose -f docker-compose.prod.yml up -d --build`。
5. Certbot または Cloudflare Proxy で TLS。

DB バックアップは [OPERATIONS.md](OPERATIONS.md) のスクリプトを cron 化し、S3 に置く。

---

## 4. 秘密情報を SSM に入れる

Parameter Store（SecureString）例（名前は `terraform.tfvars` の prefix に合わせる）:

```bash
PREFIX=/sns-x-prod

aws ssm put-parameter --name "$PREFIX/JWT_SECRET" --type SecureString \
  --value "$(openssl rand -base64 48)" --overwrite

aws ssm put-parameter --name "$PREFIX/POSTGRES_PASSWORD" --type SecureString \
  --value "（RDS 作成時と同じ強パスワード）" --overwrite

# 任意
aws ssm put-parameter --name "$PREFIX/SENTRY_DSN" --type SecureString \
  --value "https://..." --overwrite
```

ECS タスク定義はこれらの ARN を `secrets` で参照する（`infra/modules/ecs` 参照）。

RDS 起動後、一度だけ拡張を作成（psql または ECS Exec）:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

その後に API イメージをデプロイし、Alembic を走らせる。

アプリに渡す非秘密の環境変数例（ECS タスク定義に Terraform で埋め込み済み）:

```text
APP_ENV=production
POSTGRES_HOST=<rds_endpoint>
POSTGRES_PORT=5432
POSTGRES_USER=sns
POSTGRES_DB=sns_x_prod
REDIS_HOST=<redis_primary_endpoint>
REDIS_PORT=6379
CORS_ORIGINS=https://app.example.com
ALLOWED_HOSTS=api.example.com
```

```text
APP_ENV=production
POSTGRES_HOST=<rds_endpoint>
POSTGRES_PORT=5432
POSTGRES_USER=sns
POSTGRES_DB=sns_x_prod
REDIS_HOST=<redis_primary_endpoint>
REDIS_PORT=6379
CORS_ORIGINS=https://app.example.com
ALLOWED_HOSTS=api.example.com
```

---

## 5. API イメージのビルドとデプロイ

```bash
cd sns-x-api-prod
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=ap-northeast-1
ECR="$AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/sns-x-api-prod"

aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

docker build -t "$ECR:$(git rev-parse --short HEAD)" -t "$ECR:latest" .
docker push "$ECR:$(git rev-parse --short HEAD)"
docker push "$ECR:latest"

aws ecs update-service --cluster sns-x-prod --service api --force-new-deployment
aws ecs update-service --cluster sns-x-prod --service worker --force-new-deployment
```

コンテナ起動コマンドは既存 Dockerfile どおり `alembic upgrade head && uvicorn ...`。  
マイグレーションは **API タスク起動時**に走る。破壊的 migration の前は必ず RDS スナップショットを取る。

確認:

```bash
curl -sS https://api.example.com/health
curl -sS https://api.example.com/health/ready
# production では docs が 404 であること
curl -sS -o /dev/null -w "%{http_code}\n" https://api.example.com/docs
```

---

## 6. フロントエンドのビルドと配信

```bash
cd sns-x-frontend-prod
cp .env.example .env.production.local
```

`.env.production.local` 例:

```text
VITE_API_BASE_URL=https://api.example.com
VITE_OPERATOR_NAME=Your Name
VITE_CONTACT_EMAIL=support@example.com
# VITE_SENTRY_DSN=...
```

```bash
npm ci
npm run build

BUCKET=$(cd ../sns-x-api-prod/infra/envs/prod && terraform output -raw frontend_bucket)
DIST_ID=$(cd ../sns-x-api-prod/infra/envs/prod && terraform output -raw cloudfront_distribution_id)

aws s3 sync dist/ "s3://$BUCKET/" --delete \
  --cache-control "public,max-age=31536000,immutable" \
  --exclude "index.html"
aws s3 cp dist/index.html "s3://$BUCKET/index.html" \
  --cache-control "public,max-age=60,must-revalidate" \
  --content-type "text/html"

aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/index.html" "/"
```

SPA のため CloudFront では `403/404 → /index.html` のカスタムエラー（モジュール既定）が必要。

---

## 7. カットオーバーチェックリスト

- [ ] `https://app.example.com` で登録 UI・規約/PP/窓口が表示される
- [ ] 新規登録（同意チェック必須）→ ログイン → 投稿
- [ ] リフレッシュ後もセッション維持、ログアウトで失効
- [ ] `CORS` エラーがコンソールに出ない
- [ ] `/docs` が 404
- [ ] RDS 自動バックアップが有効
- [ ] 手動で一度 `pg_dump` 相当（またはスナップショット）を取得しリストア手順を空読み
- [ ] 請求ダッシュボードを翌日確認

---

## 8. 日常のデプロイ（短縮版）

| 変更 | 手順 |
|---|---|
| API のみ | ECR build/push → ECS force-new-deployment |
| FE のみ | `npm run build` → s3 sync → CloudFront invalidation |
| インフラ | `terraform plan` → `apply`（破壊的変更は休日に） |
| DB schema | API イメージに migration を含めてデプロイ（事前バックアップ） |

GitHub Actions を使う場合の流れ（推奨）:

1. `infra/` で OIDC 用 IAM ロールを作成（ドキュメントは `infra/README.md`）。
2. `api` workflow: test → build → push → ECS。
3. `frontend` workflow: test/build → s3 sync → invalidate。
4. `terraform` workflow: `plan` を PR にコメント、`apply` は `main` + environment 承認。

---

## 9. ロールバック

| 対象 | 方法 |
|---|---|
| API | 前の ECR タグでタスク定義を戻す / 以前のイメージ digest で再デプロイ |
| FE | 前の `dist` アーティファクトを sync、または S3 バージョニングから復元 |
| DB | RDS スナップショットからリストア（時間要）。アプリはメンテ表示を検討 |
| Terraform | `git revert` 後に `plan/apply`。state の手動編集はしない |

---

## 10. コスト抑制の運用メモ

- 使わない検証環境は `terraform destroy` する（prod と分けた `envs/dev` を推奨）。
- CloudWatch Logs 保持は **7–14 日**。
- NAT Gateway を足したくなったら、先にコスト試算する。
- ElastiCache / RDS を止めるときはスナップショットを残す。

---

## 関連ドキュメント

- [INFRASTRUCTURE.md](INFRASTRUCTURE.md) — 構成案
- [OPERATIONS.md](OPERATIONS.md) — バックアップ・アプリ側本番チェック
- [legal/](legal/) — 規約・PP・窓口ひな形
- [`infra/README.md`](../infra/README.md) — Terraform の使い方
