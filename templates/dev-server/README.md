# dev-server（云端开发机）

共享 Spot EC2 开发机模板（**dev env only**）：开发人员通过 SSM Session Manager 登录，无公网 IP、无 SSH 入站端口。工作日 08:30–20:30 HKT 自动开关机。

适用：需要常驻 dev 云端环境调试、或本地资源受限时统一共用一台开发机。

## 存储规格参考

| 开发人员数 | 根卷大小 |
|---|---|
| 1 | 60 GB |
| 2（默认）| 100 GB |
| 3 | 140 GB |
| 5 | 220 GB |

推荐实例：`t3.medium`（2 vCPU / 4 GB），3 人以上或有重编译场景可升 `t3.large`。

## 快速起步

1. **app-registry 登记**（一次性，如尚未登记）：确认 `app-registry/access-surface/apps.yaml` 中已有本应用条目，`app-onboarding` 承接 AppDeployRole 与 state backend contract。

2. **配置变量**：复制 `iac/variables.tf` 中的变量，在 dev tfvars 中填写：
   ```hcl
   app_name        = "my-app"
   repo_pascal     = "MyApp"
   developer_count = 2        # 按团队实际人数调整
   # instance_type = "t3.medium"  # 可选，默认 t3.medium
   ```

3. **初始化并 apply（仅 dev）**：
   ```bash
   tofu init -backend-config=backend.dev.hcl
   tofu plan -var-file=dev.tfvars
   # 确认无误后经 CI apply（本地只读）
   ```

4. **连接**：apply 完成后，用 `DevDataDebugPermissionSet` 临时凭证：
   ```bash
   aws ssm start-session --target <instance-id> --region ap-east-1
   ```
   或直接用 `tofu output ssm_connect_command` 获取完整命令。

## 注意事项

- **dev only**：`var.env` 有校验，staging/prod 禁止创建。
- **Spot 中断**：AWS 回收算力时实例自动 stop（不 terminate），EBS 数据保留，容量恢复后实例自动重启。重要工作建议定期推 git。
- **切换到 Spot 需重建**：从 on-demand 改为本模板，tofu apply 会销毁并重建实例；`delete_on_termination = false` 保留旧 EBS，但建议 apply 前备份。
- **应用专属权限**：若开发机需要访问应用数据库（RDS）、S3 等，在本应用的 `aws_iam_role.dev_server` 上追加内联 policy，不修改本模板共有逻辑。
