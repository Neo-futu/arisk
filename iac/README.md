# iac

OpenTofu（>= 1.6）配置，部署 lambda-deploy 形态的云资源到 dev/staging/prod。**只读 SSM 派生对接基础设施，禁硬编码账号/ARN。**

## 文件

| 文件 | 作用 |
|---|---|
| `versions.tf` | tofu >= 1.6；aws + archive provider |
| `providers.tf` | region=ap-east-1；`assume_role` AppDeployRole（ARN 由 `var.deploy_role_arn` 传入） |
| `backend.tf` | partial S3 backend（块留空，`tofu init -backend-config` 注入） |
| `data.tf` | 读 SSM：account_id / deploy-role-arn（校验）/ vpc-id + priv subnet（默认注释，进 VPC 时启用） |
| `main.tf` | `aws_lambda_function` + scoped exec role + CloudWatch 日志组；`archive_file` 打包 `app/` |
| `examples/` | 可复制的可选 IaC 示例，例如 bl-dev DB registry |
| `variables.tf` | app_name / repo_pascal / env / region / deploy_role_arn / lambda_* |
| `outputs.tf` | function name/arn / log group / account_id |

## SSM 对接契约（与基础设施一致）

- 账号 ID：`/landing-zone/accounts/<env>/account_id`
- VPC：`/infra/bl/<env>/ap-east-1/network/vpc-id`
- 子网：`/infra/bl/<env>/ap-east-1/network/subnet-ids/<tier>`（Lambda 进 VPC 用 `priv`）
- 部署角色 ARN：`/infra/bl/<env>/ap-east-1/platform/role-app-deploy-<RepoPascal>-<EnvPascal>-arn`

## backend（partial config）

backend 块不支持变量，故留空，init 时注入。把 `backend.<env>.hcl.example` 复制为 `backend.<env>.hcl`（已 `.gitignore`），或由 CI 生成：

```hcl
bucket         = "balance-tf-state-<env>-ap-east-1"
key            = "app/<app-name>/<env>/terraform.tfstate"
workspace_key_prefix = "app/<app-name>/<env>/workspaces"
region         = "ap-east-1"
dynamodb_table = "balance-tf-locks-<env>-ap-east-1"
encrypt        = true
```

## 本地校验（无需云凭证）

```bash
cd iac
tofu fmt -check
tofu validate -backend=false
```

部署交给 CI（`.github/workflows/deploy.yml`）：tag `v*` → OIDC 假设 AppDeployRole → init/plan/apply，dev→staging→prod。

## bl-dev DB registry 示例

如果应用拥有自己的 dev 数据库实例，建议由应用 IaC 发布 `/app/<app>/<env>/bl-dev/databases`，让开发者通过 `bl-dev shell <app>` 里的 `db targets` / `db psql --name <target>` / `db serve --name <target>` 访问。

参考 [`examples/bl-dev-db-registry.tf.example`](examples/bl-dev-db-registry.tf.example)。示例包含：

- 多 DB target 的 JSON schema。
- `endpointParameter` / `portParameter` 形式，避免 registry 直接写死 endpoint。
- `database` 和固定 IAM DB user。
- `relay.ecsCluster` + `relay.ecsService`，让 bl-dev 使用应用自己的 ECS task 作为 SSM port-forward 落点。

RDS IAM Authentication 仍然需要数据库内存在固定 user，并授予 `rds_iam` 及必要 schema/table 权限；IAM token 只替代 password。
