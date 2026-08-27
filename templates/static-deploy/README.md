# static-deploy（静态前端形态）

静态站点形态：应用自建 S3 桶 + 共享 CloudFront distribution（OAC），经 OpenTofu 部署。CI 同步构建产物到 S3 并在 prod 做 CloudFront invalidation。

适用：纯静态前端（SPA、文档站、落地页），无服务端逻辑或仅调用独立 API。

对接基础设施的通用约定与 `lambda-deploy` 一致（只读 SSM 派生、partial backend、OIDC 假设 `AppDeployRole`）。

## S3 归属与安全基线

**应用自建 S3 桶**：IaC 在应用仓 `templates/static-deploy/iac/`，由 `AppDeployRole` 创建与管理。infra 提供安全基线（SCP 强制），应用 IaC 显式声明以下配置：

| 项目 | 设置 |
|---|---|
| 桶名约定 | `<app_name>-static-<env>-ap-east-1` |
| 公网直访 | 完整禁止（`block_public_access` 四项全 true） |
| 加密 | SSE-S3/AES256（`aws:kms` 按需替换） |
| 版本控制 | 启用（允许回滚静态文件版本） |

`AppDeployRole` 按桶名前缀约定获得 `s3:*` 权限（infra platform-iam 已覆盖 `<app_name>-static-*`）。

## CloudFront（infra 集中管理）

CloudFront distribution、Global WAF、OAC（Origin Access Control）、ACM 证书均由 infra 集中管理；应用从 SSM 读取：

| 用途 | SSM 路径 | 备注 |
|---|---|---|
| CloudFront distribution ID | `/balance/ingress/external/prod/cloudfront/distribution_id` | 仅 prod |
| CloudFront 域名 | `/balance/ingress/external/prod/cloudfront/domain_name` | 仅 prod，格式 `dxxx.cloudfront.net` |

prod 桶策略（`aws_s3_bucket_policy`）用 CloudFront distribution ARN 锁定 OAC 读权限；dev/staging 无 CF，桶仅供开发者经 IAM + `bl-dev s3` 访问。

## app-registry 接入（一次性）

在 `app-registry/access-surface/apps.yaml` 中声明静态站点能力，触发平台控制面创建 OAC 并把本应用的 S3 桶注册为 CloudFront S3 origin：

```yaml
apps:
  - name: <app_name>
    capabilities:
      compute: [static-site]          # 触发 infra 创建 OAC + 注册 CF S3 origin
      ingress: [customer-web]         # 触发 prod leaf CNAME 写入 Route 53
    ingress:
      customer_fqdns: ["<app>.balancehk.com"]
```

`app-onboarding` 消费 artifact 后，infra 完成 OAC 与 CF distribution 关联，并将本应用 S3 桶加为 ordered cache behavior（按 host 隔离）。

## CI workflow 样板

把以下两个工作流放进派生仓：

### `_deploy-static-env.yml`（替代或扩展 `_deploy-env.yml`）

在 `tofu apply` 完成后追加 S3 sync 与 CF invalidation 步骤：

```yaml
# .github/workflows/_deploy-static-env.yml
name: _deploy-static-env
on:
  workflow_call:
    inputs:
      env:        { required: true, type: string }
      env_pascal: { required: true, type: string }
      gh_environment: { required: true, type: string }
      build_dir:
        description: "构建产物目录（相对仓库根）"
        default: "dist"
        type: string

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ inputs.gh_environment }}
    env:
      APP_NAME:       ${{ vars.APP_NAME }}
      REPO_PASCAL:    ${{ vars.REPO_PASCAL }}
      AWS_REGION:     ${{ vars.AWS_REGION || 'ap-east-1' }}
      AWS_ACCOUNT_ID: ${{ vars.AWS_ACCOUNT_ID }}
    steps:
      - uses: actions/checkout@v5

      - uses: opentofu/setup-opentofu@v2
        with:
          tofu_version: "1.6.2"

      - name: Configure AWS via OIDC
        uses: aws-actions/configure-aws-credentials@v6.1.3
        with:
          role-to-assume: arn:aws:iam::${{ env.AWS_ACCOUNT_ID }}:role/AppDeployRole-${{ env.REPO_PASCAL }}-${{ inputs.env_pascal }}
          aws-region: ${{ env.AWS_REGION }}
          role-session-name: ${{ env.APP_NAME }}-${{ inputs.env }}-gha

      - name: Resolve deploy role ARN from SSM
        id: ssm
        run: |
          ROLE_ARN=$(aws ssm get-parameter \
            --name "/infra/bl/${{ inputs.env }}/ap-east-1/platform/role-app-deploy-${REPO_PASCAL}-${{ inputs.env_pascal }}-arn" \
            --query 'Parameter.Value' --output text --region "${AWS_REGION}")
          echo "deploy_role_arn=${ROLE_ARN}" >> "$GITHUB_OUTPUT"

      - name: Write backend config
        run: |
          cat > iac/backend.${{ inputs.env }}.hcl <<EOF
          bucket         = "balance-tf-state-${{ inputs.env }}-ap-east-1"
          key            = "app/${APP_NAME}/${{ inputs.env }}/terraform.tfstate"
          region         = "ap-east-1"
          dynamodb_table = "balance-tf-locks-${{ inputs.env }}-ap-east-1"
          encrypt        = true
          EOF

      - name: Tofu init
        working-directory: iac
        run: tofu init -backend-config=backend.${{ inputs.env }}.hcl

      - name: Tofu plan
        working-directory: iac
        run: |
          tofu plan -input=false -out=tfplan \
            -var="app_name=${APP_NAME}" \
            -var="repo_pascal=${REPO_PASCAL}" \
            -var="env=${{ inputs.env }}" \
            -var="region=${AWS_REGION}" \
            -var="deploy_role_arn=${{ steps.ssm.outputs.deploy_role_arn }}"

      - name: Tofu apply
        working-directory: iac
        run: tofu apply -input=false -auto-approve tfplan

      # ---- 前端构建（根据项目实际替换此步骤）----
      - name: Build frontend
        run: |
          # 示例（Node.js）：
          # npm ci && npm run build
          # 示例（Hugo）：
          # hugo --minify
          echo "替换为实际构建命令，产物输出到 ${{ inputs.build_dir }}/"

      # ---- S3 sync：上传构建产物 ----
      - name: S3 sync
        run: |
          BUCKET="${APP_NAME}-static-${{ inputs.env }}-ap-east-1"
          aws s3 sync "${{ inputs.build_dir }}/" "s3://${BUCKET}/" \
            --delete \
            --cache-control "public, max-age=31536000, immutable" \
            --exclude "index.html" \
            --exclude "*.html"
          # HTML 文件不设长期缓存（CloudFront 需能刷新入口）
          aws s3 sync "${{ inputs.build_dir }}/" "s3://${BUCKET}/" \
            --exclude "*" \
            --include "*.html" \
            --cache-control "no-cache"

      # ---- CloudFront invalidation（仅 prod）----
      - name: CloudFront invalidation
        if: inputs.env == 'prod'
        run: |
          DIST_ID=$(aws ssm get-parameter \
            --name "/balance/ingress/external/prod/cloudfront/distribution_id" \
            --query 'Parameter.Value' --output text --region "${AWS_REGION}")
          aws cloudfront create-invalidation \
            --distribution-id "${DIST_ID}" \
            --paths "/*"
```

调用方 `deploy.yml`（替换根目录 `_deploy-env.yml` 的调用）：

```yaml
jobs:
  dev:
    uses: ./.github/workflows/_deploy-static-env.yml
    with:
      env: dev
      env_pascal: Development
      gh_environment: development
      build_dir: dist
    secrets: inherit

  staging:
    needs: dev
    uses: ./.github/workflows/_deploy-static-env.yml
    with:
      env: staging
      env_pascal: Staging
      gh_environment: staging
      build_dir: dist
    secrets: inherit

  prod:
    needs: staging
    uses: ./.github/workflows/_deploy-static-env.yml
    with:
      env: prod
      env_pascal: Production
      gh_environment: production-app
      build_dir: dist
    secrets: inherit
```

## apply 后 CNAME 清单

infra dns-records stack 会自动在 Route 53 写入 prod leaf CNAME（`<app>.balancehk.com → dxxx.cloudfront.net`）。若对应域名在 DNSPod 管理，需人工在 DNSPod 配置 CNAME；CNAME 目标值从 SSM 读取：

```bash
aws ssm get-parameter \
  --name "/balance/ingress/external/prod/cloudfront/domain_name" \
  --query 'Parameter.Value' --output text --region ap-east-1
```

## 开发者 dev S3 访问

dev 桶无 CloudFront，开发者经 IdC `DevDataDebugPermissionSet` 通过 `bl-dev` 访问：

```bash
bl-dev shell <app>
# 进入 bl-dev shell 后：
s3 ls                             # 列出本应用 dev 桶（自动发现 registry）
s3 ls s3://<app>-static-dev-ap-east-1/
s3 cat s3://<app>-static-dev-ap-east-1/index.html
```

`aws_ssm_parameter.bl_dev_s3_registry` 已在 IaC 中发布（`/app/<app_name>/dev/s3-data-bucket`），`bl-dev` 自动发现。

## 本地静态校验

```bash
cd templates/static-deploy/iac
tofu fmt -check
tofu validate -backend=false
```

## 混合形态（lambda + static）

静态前端 + API Lambda 的应用在同一仓库内叠加两套 IaC：

1. 根 `iac/`：Lambda 部署（lambda-deploy 形态）。
2. `static/iac/`（或 `templates/static-deploy/iac/` 的副本）：S3 静态桶部署。

在 `app-registry` 中声明 `deployment.state.layout: monorepo-components`，并列出 component 名称与路径；`app-onboarding` 派生各 component 的独立 state key（`app/<app-name>/static/<env>/terraform.tfstate` 等）。
