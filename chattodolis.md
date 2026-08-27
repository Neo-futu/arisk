*20260827*
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
 方案（修订）：按 ideclare 结构改造 arisk —— 本地专注版

 Context

 参照已上线派生应用 ideclare 的模块设计 / 文档结构 / 派生架构改造 arisk，但不照搬 ideclare 的共享 Aurora 模型：

 已确认取舍：
 - arisk 有自己的库和服务，不消费平台共享 Aurora。保留现有本地 postgres + AWS 双模（Turn 2 的 POSTGRES_* + POSTGRES_IAM_AUTH）。
 - 云端 RDS 的 IaC provision 推迟到正式上线部署阶段；本轮专注本地业务开发与双模验证。
 - 服务整合进 backend 单进程：2_processing/6_entry/4_mcp/autorisk 作为 backend 的挂载子应用/模块，一个 FastAPI 对外（= ideclare 式单任务的运行时形态）。
 - 保留 app-template lambda 脚手架样例（app/handler.py、tests/test_handler.py、templates/、当前 lambda iac/）不动。
 - ideclare 仅作非云部分参照：docs/ 结构、scripts/、.envrc、AGENTS.md/CLAUDE.md 分节、backend 模块化设计、RDS IAM 连接技法（Turn 2 已实现）。云相关的 ECS/ALB/RDS iac 与 ECS 部署 workflows 留到上线阶段
 。

 参照绝对路径：ideclare/backend/app/{main.py,core/database.py}、ideclare/docs/{aws-deployment,database-schema}.md、ideclare/scripts/*、ideclare/AGENTS.md、ideclare/CLAUDE.md。

 关键约束：arisk 服务名以数字开头（2_processing/6_entry/4_mcp）非法 Python 标识符 → 用 importlib.import_module() 挂载，不能 import。

 执行步骤（本轮，续分支 feat/derive-from-app-template）

 1. 统一 backend 入口（核心：服务整合进单进程）

 - 新增 backend/app/unified.py：一个 FastAPI，在 app/main.py 现有 iam/业务路由之上，app.mount() 挂载 arisk 现有子应用：
   - /processing ← importlib.import_module("2_processing.api.main").app
   - /entry ← importlib.import_module("6_entry.web.app").app
   - /mcp ← 4_mcp gateway app（尽力）
   - /autorisk ← autorisk app（尽力）
   - 把 repo 根加入 sys.path；每个 mount 包 try/except（缺依赖只跳过该 mount，不整体崩），启动时日志汇报挂载结果。
   - 保留 /health。
 - 加法式、不改默认：不动 app/main.py 与现有多进程 scripts/dev.py 行为；unified.py 提供“单进程对外”能力（供后续容器/ECS 用）。
 - scripts/dev.py：新增一个 part backend-unified（跑 uvicorn app.unified:app），--list-parts/--dry-run 可见；默认 profile 不变。

 2. DB 双模保留（不动 shared Aurora、不 provision 云）

 - 保留 Turn 2 的 backend/app/core/{config.py,db.py} + alembic/env.py 双模（本地静态密码 / 云 POSTGRES_IAM_AUTH=true 走 RDS IAM token）。不改共享 Aurora、不 provision RDS。
 - 仅验证本地双模仍工作；DB_* 命名对齐与自有 RDS provision 留到上线阶段（在 docs/aws-deployment.md 写清）。

 3. ideclare 结构对齐（非云部分）

 - docs/aws-deployment.md（新增）：arisk 自有 RDS + ECS 的上线部署蓝图（参照 ideclare 但用 arisk 自有库；标注“待上线阶段落 iac/workflows”，列出 SSM 契约、镜像 app-arisk-backend/app-arisk-frontend、Secr
 ets、S3、单任务=frontend+统一 backend）。
 - docs/database-schema.md（新增）：arisk iam（Alembic）+ fsi（1_datastorage/postgres/schema + 2_processing/sql）schema 概览，指向既有 SQL 权威源。
 - scripts/bl-dev.sh（新增）：bl-dev shell arisk 包装（dev 联调）。
 - scripts/migrate-db.sh（新增）：旧库 → arisk 自有 RDS 的 dump/restore + alembic upgrade head（上线用；标注）。
 - .envrc：对齐 ideclare（source backend/.env + .venv）。
 - AGENTS.md：在现有派生前言后，重排/补齐 ideclare 式分节（Project Overview / Development Commands / Git Workflow / Environment Setup / Dev Cloud Debug Access / Architecture），写清：统一 backend 单进
 程、DB 本地/云双模且自有库、服务模块清单、云 iac 待上线。更新头（2026-08-27 / Claude Opus 4.8）。
 - CLAUDE.md：对齐 ideclare 分节（指针 + Development Commands + Environment + Architecture + Deployment），保留 arisk 业务规则。

 4. 明确不做（本轮）

 - 不把 iac/ 改成 ECS、不写 RDS/ALB/Secrets/S3/dev-server 云资源、不换 ideclare 式 ECS 部署 workflows —— 全部留到“正式上线部署阶段”，在 docs/aws-deployment.md 记为后续。
 - 不物理搬迁各服务代码进 backend/app/modules/（本轮用 mount 达成单进程；物理并入后续 Phase）。
 - 不删 lambda 脚手架样例。

 关键文件

 - 统一入口：新增 backend/app/unified.py；改 scripts/dev.py（加 backend-unified part）
 - 文档/脚本/结构：新增 docs/{aws-deployment,database-schema}.md、scripts/{bl-dev.sh,migrate-db.sh}；改 .envrc、AGENTS.md、CLAUDE.md
 - DB 双模：backend/app/core/{config,db}.py、alembic/env.py（保持 Turn 2，不动）

 复用的既有实现（参照 ideclare 绝对路径，仅取非云部分）

 - 统一/模块化 FastAPI 结构与 /health：ideclare/backend/app/main.py
 - RDS IAM 连接技法（arisk 已有等价实现）：ideclare/backend/app/core/database.py
 - 文档结构与分节：ideclare/docs/{aws-deployment,database-schema}.md、ideclare/AGENTS.md、ideclare/CLAUDE.md
 - 脚本：ideclare/scripts/{bl-dev.sh,migrate-db.sh,run_api.py}
 - （云 iac/workflows：ideclare/iac/*.tf、ideclare/.github/workflows/* —— 仅作上线阶段蓝图参照，本轮不落地）

 验证

 - 统一入口冒烟：cd backend && PYTHONPATH=<repo根>:$(pwd) python -c "import app.unified as u; print([r.path for r in u.app.routes][:10])"；缺依赖时 mount 被 try/except 跳过、进程不崩，日志列出成功/跳过
 的挂载。
 - python scripts/dev.py --list-parts 显示 backend-unified；--dry-run 显示其 uvicorn 命令。
 - DB 双模（Turn 2 回归）：本地 POSTGRES_IAM_AUTH=false → URI 带静态密码可连（DB 已起时）；true 分支 mock boto3 + do_connect 冒烟。
 - pytest tests/ -q → 仍 8 passed（lambda 样例保留）。
 - git diff --stat 复核：app/、tests/test_handler.py、templates/、iac/（lambda）、四类 postgres 部分、各服务业务代码 均未删改（本轮为纯新增 + 文档/脚本）。
 - 完成后 commit 续到分支并 push（PR #1 更新）。

 后续（上线阶段，PR 说明列出）

 - 按 ideclare 落 arisk 自有 RDS + ECS 单任务（frontend + 统一 backend）iac 与 ECS 部署 workflows（deploy/ci/migrate-db/seed-secrets/dev-server/diag/gen-presigned-url）。
 - backend DB 命名可按需对齐 DB_*；各服务业务代码物理并入 backend/app/modules/；Celery worker 形态；app-registry onboarding、仓库 Variables/Environments/分支保护。
 - 