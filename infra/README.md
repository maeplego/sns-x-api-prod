# infra — Terraform（個人開発・AWS）

`sns-x-api-prod` / `sns-x-frontend-prod` 公開用の IaC スケルトンです。

- 設計: [docs/INFRASTRUCTURE.md](../docs/INFRASTRUCTURE.md)
- 手順: [docs/DEPLOY.md](../docs/DEPLOY.md)

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
    dns/              # Route53 records
    github_oidc/      # 任意: GitHub Actions 用
```

## 前提

- Terraform `>= 1.5`
- AWS 権限: VPC / ECS / RDS / ElastiCache / S3 / CloudFront / ACM / Route53 / IAM / SSM
- ドメインを Route53 で管理できること（または検証用レコードを手動追加）

## 使い方（要約）

```bash
# 1) state バックエンド
cd bootstrap && cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply

# 2) 本番
cd ../envs/prod
cp backend.hcl.example backend.hcl   # bootstrap の出力を反映
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

## モジュールの実装状況

スケルトンは **変数・出力・リソースの骨格** までです。初回 `apply` 前に各 `modules/*/main.tf` を環境に合わせて埋めてください。コメントで推奨スペック（`db.t4g.micro` 等）を示しています。

個人開発で特に守ること:

1. **NAT Gateway を作らない**（public subnet + Fargate `assign_public_ip`）
2. RDS / Redis は private 扱いにし、SG で ECS からだけ許可
3. 秘密情報は Terraform に直書きせず SSM へ

## GitHub OIDC（任意）

`modules/github_oidc` で Actions 用ロールを作ったあと、ワークフロー例:

```yaml
permissions:
  id-token: write
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT:role/sns-x-prod-github
          aws-region: ap-northeast-1
```

長期の `AWS_ACCESS_KEY_ID` は置かないでください。
