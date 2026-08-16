# infra — Terraform（設計資料 / スケルトン）

> **重要:** このディレクトリはポートフォリオ向けの **設計資料** です。実 AWS アカウントへの `terraform apply` は本プロジェクトでは行っていません。動く公開デモの本体はローカル Docker Compose（親 README の Demo 節）です。

`sns-x-api-prod` / `sns-x-frontend-prod` を個人規模で AWS に載せる場合の **構成意図をコードで表したもの** です。

- 設計の文章: [docs/INFRASTRUCTURE.md](../docs/INFRASTRUCTURE.md)
- 手順の文章: [docs/DEPLOY.md](../docs/DEPLOY.md)

## 位置づけ

| これは | これはない |
|---|---|
| コストを抑えた構成の具体例（NAT なし、Fargate micro、RDS/Redis micro、S3+CloudFront） | 検証済みの one-click 本番環境 |
| モジュール分割・変数・出力の見本 | 課金発生を伴う必須ステップ |
| 公開するならこうする、という説明材料 | 現時点のライブインフラ |

モジュールはリソース定義まで含みますが、環境差分・IAM の最小化・初回ブートストラップなどは、実 apply 前に見直しが必要です。

## レイアウト

```text
infra/
  bootstrap/          # Terraform state 用 S3 + DynamoDB（ローカル state）
  envs/prod/          # 本番 root module
  modules/
    vpc/
    ecr/
    rds/
    redis/
    alb/
    ecs/
    frontend/         # S3 + CloudFront
    dns_records/      # Route53 aliases
    certs/            # ACM (+ us-east-1 for CloudFront)
    github_oidc/      # 任意: GitHub Actions 用
```

## 前提（もし apply するなら）

- Terraform `>= 1.5`
- AWS 権限: VPC / ECS / RDS / ElastiCache / S3 / CloudFront / ACM / Route53 / IAM / SSM
- ドメインを Route53 で管理できること

## 使い方（参考・未検証）

```bash
# 1) state バックエンド
cd bootstrap && cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply

# 2) 本番
cd ../envs/prod
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan
# terraform apply   # 課金・破壊的変更に注意。本リポでは未実施
```

個人開発で特に守ること:

1. **NAT Gateway を作らない**（public subnet + Fargate `assign_public_ip`）
2. RDS / Redis は ECS 以外から届かないよう SG を絞る
3. 秘密情報は Terraform に直書きせず SSM へ

## GitHub OIDC（任意・設計メモ）

`modules/github_oidc` は Actions 用ロールのたたき台です。長期の `AWS_ACCESS_KEY_ID` は置かない想定です。
