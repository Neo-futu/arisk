# ARISK 啟動手冊（app-template 完整派生 · PostgreSQL 本地/AWS 雲雙支持）

> 適用於當前分支狀態：arisk 已是平台脚手架 `app-template` 的**完整派生應用**，
> 忠實保留全套脚手架（`app/` + `tests/` + `iac/` + `.github/` + `templates/`）
> 並與 arisk 業務代碼（`1_datastorage`…`6_entry`、`backend/`、`frontend/`、`aiagent/`）並存。
> **PostgreSQL 連庫層支持雙模**：本地（靜態密碼 + localhost）與 AWS 雲（RDS IAM token）。
>
> 專案根目錄：`D:\vsproject\ai-balance\arisk`
> 服務職責與端口對照見 [`startup_commands_and_roles.md`](startup_commands_and_roles.md)；本手冊聚焦「派生结构 + 本地/雲啟動與驗證」。

---

## 0. 這份派生應用長什麼樣（一眼看懂）

| 類別 | 目錄 / 文件 | 說明 |
|---|---|---|
| **app-template 脚手架**（忠實保留） | `AGENTS.md`、`app/handler.py`、`tests/`、`iac/`、`.github/workflows/`、`templates/`、`.claude/`、`.envrc`、`scripts/protect-main-branch.sh` | golden-path 默認形態（lambda）+ CI/CD + 對接契約，供後續團隊一致遵循；**不要刪** |
| **arisk 業務代碼** | `1_datastorage`…`6_entry`、`backend/`、`frontend/`、`aiagent/`、`autorisk/` 等 | 真實多服務平台（風控/投研） |
| **PostgreSQL 部分**（保留 + 增強雙模） | `1_datastorage/postgres/`、`backend/app/core/{config,db,db_auth}.py`、`backend/app/alembic/`、`2_processing/sql/`、`scripts/setup_db.py` | 本地/雲雙模連庫 |

> 「派生」的治理面（SSM 契約、app↔infra 邊界、發布約定）見 [`../AGENTS.md`](../AGENTS.md) 與 [`../iac/README.md`](../iac/README.md)。

---

## 1. 前置依賴

| 依賴 | 用途 | 備註 |
|---|---|---|
| Python 3.14（backend）/ 3.12+（其它層） | backend + processing + entry | backend `requires-python >=3.14` |
| uv | backend 包管理 | `pip install uv` |
| PostgreSQL 16 | 主庫（本地） | 可本機安裝，或用下方 docker-compose |
| Redis 7 | Celery / 緩存 | docker-compose 已含 |
| Bun 或 Node 20+ | frontend | |
| Docker（可選） | 一鍵拉起 pg/redis/minio/timescale | `1_datastorage/docker-compose.yml` |
| boto3（backend 依賴，已在 `pyproject.toml`） | **僅雲上 IAM 連庫需要** | 本地默認不觸發 |

---

## 2. 環境變量（`.env`）——本地 vs AWS 雲

複製模板：

```bash
copy .env.example .env      # Windows
cp .env.example .env        # bash
```

### 2.1 本地模式（默認）

```ini
# App / Backend（必填！缺任一項 backend 啟動即報 "5 validation errors"）
PROJECT_NAME=ARISK
SECRET_KEY=dev-secret-change-me
FIRST_SUPERUSER=admin@fsi.com
FIRST_SUPERUSER_PASSWORD=admin12345
ENVIRONMENT=local

# Database（本地）
POSTGRES_SERVER=localhost      # backend 讀這個
POSTGRES_HOST=localhost        # 1_datastorage / 2_processing 讀這個（保持與上同值）
POSTGRES_PORT=5432
POSTGRES_DB=fsi_risk
POSTGRES_USER=fsi_user
POSTGRES_PASSWORD=change_me     # 本地靜態密碼

POSTGRES_IAM_AUTH=false         # 關閉 → 走靜態密碼（本地）
POSTGRES_SSLMODE=
AWS_REGION=ap-east-1
```

> ⚠️ **backend 沒有 `.env` 或缺上面必填項就會崩**（`pydantic ValidationError: PROJECT_NAME / POSTGRES_SERVER / POSTGRES_USER / FIRST_SUPERUSER / FIRST_SUPERUSER_PASSWORD`）。`.env.example` 已含這些字段，`cp .env.example .env` 後按需改密碼即可。

### 2.2 AWS 雲模式（RDS + IAM 認證，**不存靜態庫密碼**）

```ini
POSTGRES_SERVER=<your-rds-endpoint>.rds.amazonaws.com
POSTGRES_HOST=<your-rds-endpoint>.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_DB=fsi_risk
POSTGRES_USER=arisk_app_rw       # RDS 內固定 IAM DB 用戶（見 §5 前置）
POSTGRES_PASSWORD=               # 留空；口令由 IAM token 動態生成

POSTGRES_IAM_AUTH=true           # 開啟 → 連接時生成新鮮 RDS IAM token 作口令
POSTGRES_SSLMODE=require         # IAM 認證要求 TLS
AWS_REGION=ap-east-1
```

> 開啟 `POSTGRES_IAM_AUTH` 後，`backend/app/core/db.py` 會在每次新建連接時經 boto3
> `rds.generate_db_auth_token()` 生成 token（約 15 分鐘過期，自動刷新），
> Alembic 遷移同理（`backend/app/alembic/env.py`）。需要本機有可用的 AWS 憑證
> （SSO/角色，`AWS_REGION` 對應 RDS 所在區）。
>
> **範圍說明（誠實）**：雙模 IAM 目前實現在 **backend 連庫層 + Alembic**。
> `2_processing` / `aiagent` 等層仍走 `DATABASE_URL` / `POSTGRES_HOST` 直連，雲上 IAM 接入為後續工作。
> 本地聯調雲端 dev 庫，優先用平台 `bl-dev`（見 §5.2），無需在各層散落連庫腳本。

---

## 3. 本地啟動（首次）

### 3.1 拉起數據庫（二選一）

**A. Docker（推薦，一鍵含 pg/redis/minio/timescale）**

```bash
cd 1_datastorage
docker compose up -d
cd ..
```

**B. 本機已裝 PostgreSQL 16 / Redis 7**：直接進入下一步。

### 3.2 初始化庫、用戶與 Schema

```bash
# 建 fsi_user + fsi_risk 庫，並按序執行 1_datastorage/postgres/schema/*.sql
python scripts/setup_db.py
# 若 postgres 超級用戶有密碼：
# python scripts/setup_db.py --pg-superpass <你的postgres密碼>
```

### 3.3 安裝依賴 + 認證表遷移 + 建超級用戶

```bash
cd backend
uv sync
alembic upgrade head            # iam schema（Alembic）
python app/initial_data.py      # 建 admin@fsi.com 超級用戶
cd ..

# 前端（本倉鎖文件是 package-lock.json → 用 npm；dev.py 也是 npm run dev）
cd frontend && npm install && cd ..
```

> `frontend/node_modules` 未安裝時 `dev.py` 會報 `'vite' is not recognized`——先在 `frontend/` 跑一次 `npm install`。

### 3.4 一鍵啟動（完整參數）

`scripts/dev.py`（跨平台）與 `scripts/dev.ps1`（PowerShell 包裝）支持完全相同的一組參數。

#### 3.4.0 兩種運行模式（先看這裡）

arisk 有兩種本地運行形態，**端口數不同是有意為之**：

| 模式 | 命令 | 端口 | 何時用 |
|---|---|---|---|
| **① ideclare 式單端口（unified）** | `python scripts/dev.py --parts backend-unified frontend` | backend `:8000`（挂 `/processing`,`/entry`,`/mcp`,`/autorisk`）+ 前端 `:5173` | 想要「一個 backend 對外」= ideclare 單 ECS 任務的形態；上線即此形態（nginx:80 + backend:8000） |
| **② 多進程開發（分端口）** | `python scripts/dev.py`（profile web）或顯式 `--parts processing entry backend frontend ...` | 每個服務各自端口（8001/8010/8000/5173/8002/8100…） | 想單獨調試/熱重載某個服務時；**你顯式列了 8 個 part，它就起 8 個**——這是預期行為 |

> **為什麼 `--parts processing entry backend frontend autorisk mcp-gateway internal-mcp wind-mcp` 起了這麼多服務？** 因為該命令**逐個點名**了 8 個 part（模式②的全量調試）。要「同一個端口」用**模式①的 `backend-unified`**。
>
> **單端口自足**：`backend-unified` 下 `PROCESSING_API_URL`/`ENTRY_API_URL` 已指回本進程的 `:8000/processing`、`:8000/entry`（見 `scripts/dev.py`），backend 的 FSI 代理與 entry 子應用都回環到自己，不需要獨立的 8001/8010。
>
> 子應用掛在子路徑：processing 路由變為 `/processing/...`、entry 為 `/entry/...`；`GET :8000/unified/health` 查看掛載結果。

```bash
# 模式① ideclare 式單端口（推薦驗證「融合成一個 backend」）
python scripts/dev.py --parts backend-unified frontend
```
```powershell
./scripts/dev.ps1 -Parts backend-unified,frontend
```

#### 3.4.1 Profile（服務組合，模式②多進程）

| Profile | 包含服務 | 適用場景 |
|---|---|---|
| `web`（默認） | processing + **entry** + backend + frontend | 日常前後端開發 |
| `agent` | processing + **entry** | 只調試 Agent/LLM，不啟前端 |
| `full` | processing + entry + backend + frontend + **mcp-gateway + internal-mcp + wind-mcp** | 含 MCP 全套的完整環境 |

```bash
python scripts/dev.py                     # 默認 profile=web
python scripts/dev.py --profile agent     # 只 processing+entry
python scripts/dev.py --profile full      # web + MCP 全套
```
```powershell
./scripts/dev.ps1 -Profile web
./scripts/dev.ps1 -Profile agent
./scripts/dev.ps1 -Profile full
```

啟動後訪問：前端 http://localhost:5173 ｜ Backend http://localhost:8000/docs ｜ 6_entry http://localhost:8010/docs ｜ Processing http://localhost:8001/docs

#### 3.4.2 附加模塊開關（疊加到當前 profile）

| bash 旗標 | PowerShell | 作用 | 端口 |
|---|---|---|---|
| `--with-mcp` | `-WithMcp` | MCP 全套（gateway + internal + wind） | 8002 + stdio |
| `--with-mcp-gateway` | `-WithMcpGateway` | 只加 MCP Gateway | 8002 |
| `--with-internal-mcp` | `-WithInternalMcp` | 只加 internal MCP | stdio |
| `--with-wind-mcp` | `-WithWindMcp` | 只加 Wind 行情 MCP | stdio |
| `--with-autorisk` | `-WithAutorisk` | AutoRisk 模塊 | 8100 |

```bash
python scripts/dev.py --profile web --with-mcp-gateway     # AI 走統一 MCP 入口（推薦調試）
python scripts/dev.py --profile web --with-mcp             # MCP 全套
python scripts/dev.py --profile web --with-autorisk        # 前端 /autorisk 入口需要（8100）
python scripts/dev.py --profile full --with-wind-mcp       # 完整環境 + Wind 行情
```
```powershell
./scripts/dev.ps1 -Profile web -WithMcpGateway
./scripts/dev.ps1 -Profile web -WithMcp
./scripts/dev.ps1 -Profile web -WithAutorisk
```

#### 3.4.3 顯式 parts / 排除服務 / 乾跑

`--parts` 直接指定要啟的部分（**覆蓋** profile）；可用部分：`processing entry backend frontend autorisk mcp-gateway internal-mcp wind-mcp`。

```bash
python scripts/dev.py --list-parts                                     # 列出所有 parts 與 profiles
python scripts/dev.py --parts processing entry backend frontend        # 顯式最清楚
python scripts/dev.py --parts processing entry backend frontend autorisk mcp-gateway internal-mcp wind-mcp   # 模式②全量多進程（各服務獨立端口，調試用；非單端口）
python scripts/dev.py --parts autorisk                                 # 只補啟 AutoRisk（基礎服務已在跑時）
python scripts/dev.py --parts processing backend frontend --no-entry   # 跳過 6_entry（Chat 不可用）
python scripts/dev.py --profile web --dry-run                          # 只打印計劃，不真正啟動
```
```powershell
./scripts/dev.ps1 -ListParts
./scripts/dev.ps1 -Parts processing,entry,backend,frontend
./scripts/dev.ps1 -Parts processing,entry,backend,frontend,autorisk,mcp-gateway,internal-mcp,wind-mcp
./scripts/dev.ps1 -Only entry                                          # 只啟單個服務
./scripts/dev.ps1 -Parts processing,backend,frontend -DryRun
```

其它排除開關：`--no-frontend` / `--no-backend` / `--no-entry` / `--no-processing`（PowerShell：`-NoFrontend` / `-NoBackend` / `-NoEntry` / `-NoProcessing`）。

#### 3.4.4 常用整套命令（直接複製）

```bash
# A. Web + MCP 全套（gateway + internal + wind）
python scripts/dev.py --profile web --with-mcp
# B. 完整 profile（已含 mcp-gateway/internal/wind）
python scripts/dev.py --profile full
# C. 顯式 parts，含 AutoRisk + MCP 全套（最清楚）
python scripts/dev.py --parts processing entry backend frontend autorisk mcp-gateway internal-mcp wind-mcp
```
```powershell
./scripts/dev.ps1 -Profile web -WithMcp
./scripts/dev.ps1 -Profile full
./scripts/dev.ps1 -Parts processing,entry,backend,frontend,autorisk,mcp-gateway,internal-mcp,wind-mcp
```

啟動 `mcp-gateway` 時本地應有：`MCP_GATEWAY_URL=http://127.0.0.1:8002`，健康檢查 `http://127.0.0.1:8002/health`，工具列表 `http://127.0.0.1:8002/tools`。
AutoRisk 起後：前端整合入口 http://localhost:5173/autorisk ｜ 演示頁 http://localhost:8100/demo ｜ API http://localhost:8100/docs。

> 各服務職責、6_entry 為何不可省、MCP/審批鏈路冒煙等背景見 [`startup_commands_and_roles.md`](startup_commands_and_roles.md)。

---

## 4. 驗證（你可以直接複製運行）

### 4.1 派生脚手架自檢（無需雲憑證、無需 DB）

```bash
# (a) IaC 離線校驗（OpenTofu 1.12：-backend=false 是 init 的旗標，validate 不接受）
cd iac
tofu fmt -check
tofu init -backend=false -input=false      # 離線初始化 provider，不連 state 後端
tofu validate                               # 期望：Success! The configuration is valid.
cd ..

# (b) app-template 默認 pytest 門檻（lambda handler 樣例，僅需 pytest；handler 只用標準庫）
pip install -r tests/requirements-dev.txt   # 若系統已有 pytest 可略
pytest tests/ -q                            # 期望：8 passed
```

### 4.2 PostgreSQL 連庫層雙模自檢（核心）

`backend/scripts/check_db.py` 不存在也沒關係——用下面的一次性腳本驗證連庫層行為。
在 `backend/` 目錄、`.env` 已配好的前提下運行：

```bash
cd backend
# 本地模式（.env 內 POSTGRES_IAM_AUTH=false）：應打印含靜態口令的連接串並成功連庫
python -c "from app.core.db import engine; \
print('URL =', engine.url); \
import sqlalchemy as sa; \
[print('DB OK ->', c.execute(sa.text('select current_user, current_database()')).one()) for c in [engine.connect()]]"
```

- **本地**（`POSTGRES_IAM_AUTH=false`）：連接串形如 `postgresql+psycopg://fsi_user:***@localhost:5432/fsi_risk`，`DB OK -> ('fsi_user','fsi_risk')`。
- **雲上**（`POSTGRES_IAM_AUTH=true`，且本機有 AWS 憑證 + RDS 可達）：連接串無靜態口令（`...fsi_user@<rds>:5432/...`），連接時自動注入 IAM token、`sslmode=require`；同樣打印 `DB OK`。

> 純邏輯回歸（不連真庫，驗證「本地保留密碼 / 雲去密碼 / token 參數透傳 / do_connect 事件」）：見本倉提交 `feat(db)` 的冒煙測試思路，或運行 backend 單測。

### 4.3 業務鏈路冒煙（服務已起）

```bash
curl http://127.0.0.1:8000/api/v1/utils/health-check/
curl http://127.0.0.1:8010/agent/v2/models
curl "http://127.0.0.1:8010/query/risk/var-compare/BHMMF001?as_of_date=2026-06-25"
```

---

## 5. AWS 雲連接（RDS + IAM）

### 5.1 前置（一次性，人工 / 後續 IaC）

1. RDS 開啟 IAM 認證（`iam_database_authentication_enabled = true`）。
2. 庫內建固定 IAM DB 用戶並授權：
   ```sql
   CREATE USER arisk_app_rw;
   GRANT rds_iam TO arisk_app_rw;
   -- 按需授 fsi_risk 庫 / schema 權限
   ```
3. 部署身份（`AppDeployRole-Arisk-*`）具備 `rds-db:connect` IAM 權限（覆蓋該 DB 用戶資源）。
4. 本機具備可用 AWS 憑證（SSO），`AWS_REGION` 對應 RDS 所在區（`ap-east-1`）。

> 真實 RDS provision + 三角色分離（`*_db_owner` / `*_app_rw` / `*_ro`）+ db-init 見
> `templates/monorepo-ecs/shared/iac/{postgres.tf,db_roles.tf}`，後續按 monorepo-ecs 單獨落地。

### 5.2 開發者聯調 dev 雲庫（推薦 bl-dev，不自建跳板機）

```bash
bl-dev shell arisk
bl-dev(arisk)> db targets                 # 查看發布的 DB target
bl-dev(arisk)> db serve                    # 本地代理，自動刷新 RDS IAM token（GUI 連 127.0.0.1:15432）
bl-dev(arisk)> db psql                     # 一次性 CLI
```

> bl-dev DB registry 樣例見 `iac/examples/bl-dev-db-registry.tf.example`（`database=fsi_risk`、IAM user、SSM 間接）。

---

## 6. 端口清理與排障

```powershell
# 清理常用端口
@(8001, 8010, 8000, 5173, 8002, 8100) | ForEach-Object {
    $conn = Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue
    if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Write-Host "Killed port $_" }
}
```

| 症狀 | 排查 |
|---|---|
| backend 啟動報 `POSTGRES_SERVER` 缺失 | `.env` 需同時設 `POSTGRES_SERVER` 與 `POSTGRES_HOST`（同值） |
| 雲模式 `NoCredentialsError` / token 生成失敗 | 本機 AWS 憑證未就緒；先完成 SSO 登入，確認 `AWS_REGION` |
| 雲模式連接被拒 / 超時 | RDS SG 未放行、未開 IAM 認證、或 DB 用戶未 `GRANT rds_iam` |
| `tofu validate` 失敗 | 在 `iac/` 目錄運行；本地無需雲憑證（`-backend=false`） |
| Chat 報 `httpx.ConnectError` | 6_entry(8010) 未啟動，見 [`startup_commands_and_roles.md`](startup_commands_and_roles.md) §2 |
| Dashboard 白屏 `Cannot read properties of undefined (reading 'length')` / `/api/v1/logs/batch 404` | 前端 `/api` 未代理到 backend。已在 `frontend/vite.config.ts` 配 `server.proxy['/api'] → http://localhost:8000`；若改了後端地址，設 `VITE_API_URL`。（GET 會被 vite SPA fallback 成 HTML 導致該崩潰，POST 則 404） |

---

## 7. 如何驗證「app-template 完全派生架構」與 arisk 融合

> **先講清楚一件事**：app-template 派生架構是**倉庫結構 + 治理 + CI/CD + IaC 契約層**，
> **不是一個會啟動的運行時服務，也沒有自己的 UI**。你在瀏覽器看到的界面（`:5173`）
> 是 **arisk 自己的產品前端**；「派生」不新增界面，而是**包裹/規範** arisk 的真實服務。
> 所以「驗證派生」= 看**結構是否齊全 + 契約是否可校驗 + CI 是否綠**，不是去點某個頁面。

### 7.1 派生架構由哪些模塊組成（arisk 現在都有）

| 派生模塊 | 路徑 | 角色 | 運行時？ |
|---|---|---|---|
| 平台 AI 上下文/契約 | `AGENTS.md` | app↔infra 邊界、SSM 契約、發布約定 | 否（文檔） |
| Golden-path 應用樣例 | `app/handler.py`、`tests/test_handler.py` | app-template 默認 lambda 形態樣例 | 否（樣例，非 arisk 服務） |
| 只讀對接 IaC | `iac/`（`data.tf` SSM 讀取、`examples/bl-dev-db-registry.tf.example`） | 對接雲資源、發布 bl-dev registry | 否（IaC，CI 時 apply） |
| CI / CD | `.github/workflows/{ci.yml,deploy.yml,_deploy-env.yml}`、`.github/pull_request_template.md` | PR 門檻 + tag 逐環境發布（OIDC） | 否（GitHub Actions） |
| 部署形態樣例庫 | `templates/`（lambda / ecs / monorepo-ecs / static / dev-server / futu-adapter） | 後續真實形態的參考骨架 | 否 |
| AI / 本地工具 | `.claude/settings.json`、`.envrc` | Claude Code 設定、目錄環境 | 否 |
| 分支保護 | `scripts/protect-main-branch.sh` | 一鍵設 main 保護 | 否 |
| 兼容入口指針 | `CLAUDE.md` 頂部塊 → `AGENTS.md` | 讓 AI 先讀契約 | 否 |
| **業務代碼（arisk）** | `1_datastorage`…`6_entry`、`backend/`、`frontend/`、`aiagent/` … | 真實運行時服務 | **是** |

「融合」= 上表**派生層與業務層並存於同一倉**：派生層規範/發布，業務層照常運行，互不侵入。

### 7.2 結構驗證（一條命令看齊不齊）

```bash
cd D:/vsproject/ai-balance/arisk
for p in AGENTS.md app/handler.py tests/test_handler.py iac/data.tf \
  .github/workflows/ci.yml .github/workflows/deploy.yml templates/monorepo-ecs \
  .claude/settings.json .envrc scripts/protect-main-branch.sh; do
  [ -e "$p" ] && echo "OK   $p" || echo "MISS $p"
done
# 業務層仍在（融合證據）
for p in backend/app 1_datastorage/postgres 2_processing/sql frontend/src aiagent; do
  [ -e "$p" ] && echo "OK   $p" || echo "MISS $p"; done
```

全部 `OK` 即代表：派生脚手架齊全 **且** arisk 業務代碼並存 = 完全派生 + 融合。

### 7.3 契約 / 質量驗證（離線，無需雲憑證）

```bash
# app-template CI 門檻樣例（lambda handler）
pytest tests/ -q                                   # 期望 8 passed

# 只讀對接 IaC 可校驗
cd iac && tofu init -backend=false -input=false && tofu validate && cd ..   # Success!

# 派生留痕（兩輪提交 + PR）
git log --oneline -3
```

### 7.4 CI 驗證（GitHub 界面）

打開 PR（本分支 `feat/derive-from-app-template` → PR #1）：`ci.yml` 的 `pytest tests/` 作為合入門檻運行；`pull_request_template.md` 的架構 checklist 出現在 PR 描述——這是「派生」在**協作界面**上的可見證據。

### 7.5 融合的「界面」驗證（arisk 自己的 UI）

派生層本身沒有界面；要在界面上確認「派生沒有破壞 arisk、二者融合正常」，就是**正常啟動 arisk 前端並訪問**（需先完成 §3 的 `.env` + `npm install` + DB 初始化）：

- http://localhost:5173 —— arisk Dashboard / Chat（業務 UI）
- http://localhost:8000/docs —— backend（連庫層即 §1 的 postgres 本地/雲雙模）
- http://localhost:8100/autorisk 或 http://localhost:5173/autorisk —— AutoRisk 融合入口

PostgreSQL 雙模的「看得見」證據（§4.2 已給命令）：本地連接串帶靜態口令、雲上不帶（走 IAM token）。

---

## 8. 一句話記憶

`frontend` 展示 → `backend` 認證（連庫：本地靜態密碼 / 雲 RDS IAM token）→ `6_entry` 思考（LLM）→ `processing` 計算 → `PostgreSQL` 取數。
派生層（`AGENTS.md`/`iac`/CI/`templates`）在**倉庫與協作面**規範這一切，不在運行時露臉。
