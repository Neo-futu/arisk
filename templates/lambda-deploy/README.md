# lambda-deploy（默认形态）

Serverless 函数形态：一个 Python Lambda + scoped 执行角色 + CloudWatch 日志组，经 OpenTofu 部署到 dev/staging/prod。最轻、冷启动友好、无需常驻容器。

## 这个形态的实现就在仓库根

为了让派生仓"开箱即跑"，lambda-deploy 的实现没有放在本子目录，而是直接落在仓库根的标准位置：

| 位置 | 内容 |
|---|---|
| `app/` | 最小 Lambda handler（`handler.py`，hello + health 两路由，仅标准库） |
| `tests/` | handler 的 pytest 单测 + `data/events.json` 测试事件 |
| `iac/` | OpenTofu：`versions/providers/backend/data/main/variables/outputs.tf` |
| `.github/workflows/` | `ci.yml`（PR 跑 pytest）+ `deploy.yml`/`_deploy-env.yml`（tag 逐环境发布） |

`ecs-deploy`、`static-deploy` 子目录目前是 stub README（后续补全各自的 `iac/` 与示例代码）。

## iac/ 如何对接基础设施

- **provider**：`region=ap-east-1`，`assume_role` 假设 `AppDeployRole-<RepoPascal>-<EnvPascal>`（ARN 由 `var.deploy_role_arn` 传入，CI 从 SSM 读出注入）。
- **data.tf 只读 SSM 派生**（不硬编码账号/ARN）：
  - 账号 ID：`/landing-zone/accounts/<env>/account_id`
  - 部署角色 ARN（一致性校验）：`/infra/bl/<env>/ap-east-1/platform/role-app-deploy-<RepoPascal>-<EnvPascal>-arn`
  - VPC / 私有子网（默认注释，Lambda 进 VPC 时启用）：`/infra/bl/<env>/ap-east-1/network/vpc-id`、`.../network/subnet-ids/priv`
- **backend**：partial S3 backend，`tofu init -backend-config=backend.<env>.hcl`；桶 `balance-tf-state-<env>-ap-east-1`、锁表 `balance-tf-locks-<env>-ap-east-1`、key `app/<app-name>/<env>/terraform.tfstate`。

## 本地跑一遍（不部署）

```bash
# 测试
python -m venv .venv && . .venv/bin/activate
pip install -r tests/requirements-dev.txt
pytest tests/ -q

# IaC 静态校验（无需云凭证）
cd iac
tofu fmt -check
tofu validate -backend=false
```

## 何时改用其它形态

- 需要长驻进程 / 自定义运行时 / 高并发常驻 → `ecs-deploy`。
- 纯静态前端（SPA / 文档站）→ `static-deploy`（CloudFront + S3）。
