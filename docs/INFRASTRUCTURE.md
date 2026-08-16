# Infrastructure (個人開発向け・AWS + Terraform)

個人規模の公開を前提にした構成案です。学習用リポジトリには入れず、**この本番フォーク**と `infra/` で管理します。

> 目安コストは東京リージョン・少トラフィック時の概算です。実費は利用量・為替で変わります。

## 設計方針

| 方針 | 内容 |
|---|---|
| 小さく始める | EKS / Aurora / Multi-AZ / WAF は最初は使わない |
| NAT を避ける | **NAT Gateway（月〜$32+）は個人開発の固定費杀手**。Fargate は public subnet + パブリック IP |
| フロントは静的 | Vite ビルドを **S3 + CloudFront**（コンテナ不要） |
| 秘密情報は SSM | Secrets Manager より **SSM Parameter Store (SecureString)** を優先 |
| IaC | Terraform。状態は S3 + DynamoDB lock（最初だけ手動で bootstrap） |
| 観測 | まずは CloudWatch Logs + 任意の Sentry。Prometheus/Grafana は後回しでよい |

## 構成の二段階

### Phase 0 — 最安で公開検証（任意）

単一の小型 VM に `docker-compose.prod.yml` 相当を載せる。

```text
Internet → Lightsail または EC2 (t4g.small)
             ├─ nginx (TLS / 静的 FE or reverse proxy)
             ├─ api + worker (Compose)
             ├─ Postgres (pgvector) + volume
             └─ Redis + volume
```

| 項目 | 推奨 |
|---|---|
| 用途 | 「まず URL を出す」「友人テスト」 |
| 月額目安 | **$10–25**（Lightsail $10 プラン〜） |
| Terraform | インスタンス・SG・Elastic IP・（任意）Route53 |
| 向き | バックアップと更新を自分で回せる間 |

**向きでないとき:** 同時接続が増える / DB をマネージドにしたい / デプロイを CI に寄せたい → Phase 1。

### Phase 1 — 推奨公開構成（Terraform 本線）

```text
                         ┌─────────────┐
  users ──HTTPS──► Route53 │  A/AAAA    │
                         └──────┬──────┘
                ┌───────────────┴────────────────┐
                ▼                                ▼
         CloudFront                         ACM (証明書)
         (SPA キャッシュ)                         │
                │                                │
                ▼                                ▼
              S3                            Application
         (frontend dist)                    Load Balancer
                                                 │
                                    ┌────────────┴────────────┐
                                    ▼                         ▼
                             ECS Fargate                 ECS Fargate
                             service: api                service: worker
                             (0.25 vCPU)                 (0.25 vCPU)
                                    │                         │
                                    └────────────┬────────────┘
                                                 │
                         ┌───────────────────────┼───────────────────────┐
                         ▼                       ▼                       ▼
                   RDS PostgreSQL          ElastiCache            ECR (images)
                   16 + pgvector           Redis                  + CloudWatch
                   db.t4g.micro            cache.t4g.micro        Logs
                   single-AZ
```

| コンポーネント | 選定 | メモ |
|---|---|---|
| リージョン | `ap-northeast-1` | 国内向け |
| フロント | S3 + CloudFront + ACM | `VITE_API_BASE_URL=https://api.example.com` でビルド |
| API / worker | ECS Fargate × 2 サービス | 既存 `Dockerfile` をそのまま利用 |
| LB | ALB (HTTPS) | ヘルスチェック `GET /health` |
| DB | RDS PostgreSQL 16 | **pgvector** 拡張を有効化。single-AZ・20–50GB gp3 |
| Redis | ElastiCache Redis | レート制限・セッション系。`cache.t4g.micro` |
| ネットワーク | 1 VPC / 2 AZ の public subnet | **NAT なし**。タスクに `assign_public_ip=true` |
| 秘密情報 | SSM Parameter Store | `JWT_SECRET`, DB パスワードなど |
| DNS | Route53 | `app.` → CloudFront、`api.` → ALB |
| CI/CD | GitHub Actions + OIDC | 長期アクセスキーを置かない |
| 監視 | CloudWatch + 任意 Sentry | `/metrics` の常設 Grafana は後でよい |

**月額目安（アイドル寄り）:** だいたい **$55–90**  
内訳イメージ: ALB ~$16 + Fargate 小 ×2 ~$15–25 + RDS micro ~$12–18 + Redis micro ~$12 + CF/S3/ログ 少額。  
トラフィックやスナップショット増で上がります。

## 明示的にやらないこと（初期）

- EKS / ECS EC2 キャパシティプロバイダの複雑化
- Aurora Serverless（個人には過剰になりやすい）
- Multi-AZ RDS（可用性よりコスト優先。バックアップは必須）
- NAT Gateway / VPC Lattice など固定費の大きいネット機器
- 本番での OpenAPI 公開（既存どおり `APP_ENV=production` で隠す）
- 学習リポジトリへのインフラコード混入

## ドメイン・CORS・Trusted Host

公開後の典型値:

| 変数 | 例 |
|---|---|
| フロント | `https://app.example.com` |
| API | `https://api.example.com` |
| `CORS_ORIGINS` | `https://app.example.com` |
| `ALLOWED_HOSTS` | `api.example.com` |
| `VITE_API_BASE_URL` | `https://api.example.com` |
| `VITE_OPERATOR_NAME` / `VITE_CONTACT_EMAIL` | 窓口ページ用 |

## セキュリティ（個人でも最低限）

1. ALB / SG: インターネットから **443 のみ**（ALB）。RDS・Redis は **ECS タスク SG からのみ**。
2. `JWT_SECRET` ≥ 32 文字・ランダム。起動時の弱秘密拒否に依存してよい。
3. RDS: 自動バックアップ 7 日、暗号化 on。
4. コンテナ: 非 root 実行は今後の改善項目。まずはイメージを ECR のプライベートに。
5. GitHub OIDC で `terraform apply` / `ecs update-service`。AWS キーをリポジトリに置かない。
6. 公開前: [OPERATIONS.md](OPERATIONS.md) のチェックリスト + 法務ひな形のレビュー。

## Terraform レイアウト

リポジトリ内: [`infra/`](../infra/README.md)

```text
infra/
  bootstrap/     # state 用 S3 + DynamoDB（一度だけ）
  envs/prod/     # 本番 root module
  modules/       # vpc, ecs, rds, redis, frontend, dns ...
```

詳細手順は [DEPLOY.md](DEPLOY.md)。

## Phase 0 → Phase 1 の移行メモ

1. RDS を先に立て、`pg_dump` → `pg_restore`（[OPERATIONS.md](OPERATIONS.md)）。
2. Redis は空でよい（レート制限カウンタは揮発で問題ない想定）。
3. DNS を CloudFront / ALB に切り替え、TTL を事前に短くする。
4. 旧 VM はカットオーバー後に停止 → 削除。

## 次の伸ばし方（必要になってから）

| 症状 | 打ち手 |
|---|---|
| API CPU 不足 | Fargate CPU/メモリ増 or api desired_count=2 |
| DB 逼迫 | インスタンスクラス上げ / 読み取り用途の整理 |
| 可用性要件 | RDS Multi-AZ、AZ またぎタスク |
| 悪用・ボット | WAF / より厳しいレート制限 |
| 観測不足 | AMP + Grafana、または既存 compose 観測を別アカウントで |
