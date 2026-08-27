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

# 前端
cd frontend && bun install && cd ..
```

### 3.4 一鍵啟動全部服務

```bash
python scripts/dev.py                 # 默認 profile=web：processing+entry+backend+frontend
# 或
./scripts/dev.ps1 -Profile web        # PowerShell
```

啟動後：

- 前端 UI：http://localhost:5173
- Backend API：http://localhost:8000/docs
- 6_entry：http://localhost:8010/docs
- Processing：http://localhost:8001/docs

> profile / parts 詳解、MCP、AutoRisk(8100) 見 [`startup_commands_and_roles.md`](startup_commands_and_roles.md) §3。

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

---

## 7. 一句話記憶

`frontend` 展示 → `backend` 認證（連庫：本地靜態密碼 / 雲 RDS IAM token）→ `6_entry` 思考（LLM）→ `processing` 計算 → `PostgreSQL` 取數。
