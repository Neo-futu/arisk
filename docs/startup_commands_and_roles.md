# FSI Local Startup Commands And Roles

本文件整理本次在 VS Code terminal 實際使用的啟動命令、對應服務角色、端口、用途與驗證結果。

## 1. 服務與端口對照

| 服務 | 端口 | 角色 | 說明 |
|---|---:|---|---|
| 2_processing | 8001 | 計算核心 | 風控計算、VaR、持倉與 SQL 核心 API |
| 6_entry | 8010 | 內部入口 | Agent / Direct / CLI / Excel 內部接入層 |
| backend | 8000 | 對外後端 | JWT、對外 API、代理到 processing / entry |
| frontend | 5173 | 對外前端 | 唯一 Web UI（Dashboard + Chat） |

## 2. 實際啟動命令（本次）

### 2.1 啟動 2_processing（8001）

```powershell
Set-Location "d:\vsproject\arisk"
$env:DATABASE_URL='postgresql+asyncpg://fsi_user:change_me@localhost:5432/fsi_risk'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn 2_processing.api.main:app --host 127.0.0.1 --port 8001
```

作用：啟動計算核心 API，供 6_entry 和 backend 下游調用。

### 2.2 啟動 6_entry（8010）

```powershell
Set-Location "d:\vsproject\arisk"
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn 6_entry.web.app:app --host 127.0.0.1 --port 8010
```

作用：啟動內部入口 API，承接 Agent / Direct 請求並對接 processing。

### 2.3 啟動 backend（8000）

```powershell
Set-Location "d:\vsproject\arisk\backend"
$env:ENTRY_API_URL='http://127.0.0.1:8010'
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

作用：啟動對外 FastAPI 層，提供前端可用的統一 API。

注意：本次 backend 啟動前，補了依賴與兼容修正。

### 2.4 啟動 frontend（5173）

```powershell
Set-Location "d:\vsproject\arisk\frontend"
npm run dev
```

作用：啟動唯一 Web UI（Vite 開發服務）。

## 3. 啟動過程中的補充命令（本次）

### 3.1 清理端口占用

```powershell
# 目標端口：8001, 8010, 8000, 5173
Get-NetTCPConnection -LocalPort <port> -State Listen
Stop-Process -Id <pid> -Force
```

作用：避免端口被舊進程占用，確保四服務可按順序啟動。

### 3.2 補 backend 缺失依賴

```powershell
Set-Location "d:\vsproject\arisk\backend"
pip install "fastapi[standard]>=0.138.1,<1.0.0" "sentry-sdk[fastapi]>=2.0.0,<3.0.0"
```

```powershell
pip install "sqlmodel>=0.0.39,<1.0.0" "psycopg[binary]>=3.1.13,<4.0.0" "emails>=1.1.2,<2.0" "python-multipart>=0.0.27,<1.0.0" "email-validator>=2.1.0.post1,<3.0.0" "tenacity>=8.2.3,<10.0.0" "pyjwt>=2.13.0,<3.0.0" "pwdlib[argon2,bcrypt]>=0.3.0" "jinja2>=3.1.4,<4.0.0"
```

作用：解決 backend 啟動時的 sentry_sdk / sqlmodel 缺失。

### 3.3 backend 模型啟動錯誤修正（已改）

文件：backend/app/models.py

變更：文件頭新增

```python
from __future__ import annotations
```

作用：修復 SQLModel 關聯類型在 Python 3.13 下的前向引用 NameError。

## 4. 驗證命令與結果

### 4.1 驗證 health/docs

已驗證通過：

- 2_processing docs: http://127.0.0.1:8001/docs
- backend health: http://127.0.0.1:8000/api/v1/utils/health-check/
- backend docs: http://127.0.0.1:8000/docs
- frontend root: http://localhost:5173/
- 6_entry docs: http://127.0.0.1:8010/docs

補充：6_entry 的 /health 在本次運行版本中返回 404，但不影響 docs 與業務路由可用。

### 4.2 驗證業務鏈路（entry -> processing）

已驗證通過：

- GET http://127.0.0.1:8010/query/risk/var-compare/BHMMF001?as_of_date=2026-06-25
- 返回 200，且 results 有值

## 5. 建議的日常啟動方式

### 一鍵（推薦）

```powershell
./scripts/dev.ps1 -Profile web
```

或

```bash
python scripts/dev.py --profile web
```

## 5.1 啟動腳本參數（可選）

### Python 版本

```bash
# 列出可啟動部分與 profile
python scripts/dev.py --list-parts

# 按 profile 啟動
python scripts/dev.py --profile web
python scripts/dev.py --profile agent
python scripts/dev.py --profile full

# 僅啟動單個部分
python scripts/dev.py --only backend

# 一次啟動多個指定部分（覆蓋 profile）
python scripts/dev.py --parts processing backend frontend

# 僅查看將要執行的命令，不真正啟動
python scripts/dev.py --parts processing backend frontend --dry-run

# 在 profile 基礎上附帶 MCP
python scripts/dev.py --profile web --with-internal-mcp --with-wind-mcp
```

### PowerShell 版本

```powershell
# 列出可啟動部分
./scripts/dev.ps1 -ListParts

# 按 profile 啟動
./scripts/dev.ps1 -Profile web
./scripts/dev.ps1 -Profile agent
./scripts/dev.ps1 -Profile full

# 僅啟動單個部分
./scripts/dev.ps1 -Only backend

# 一次啟動多個指定部分
./scripts/dev.ps1 -Parts processing,backend,frontend

# 乾跑（只打印計劃）
./scripts/dev.ps1 -Parts processing,backend,frontend -DryRun
```

### 單服務

```powershell
./scripts/dev.ps1 -Only processing
./scripts/dev.ps1 -Only entry
./scripts/dev.ps1 -Only backend
./scripts/dev.ps1 -Only frontend
```

## 6. 各層作用總結

- frontend：對使用者顯示頁面（Web UI）
- backend：對外 API 與認證層（給 frontend 調用）
- 6_entry：內部 Agent/Direct 入口層
- 2_processing：計算和數據查詢核心層
- 4_mcp：工具接入層（Wind / internal DB 的 MCP）
- 3_skills：技能資產層（無常駐進程）
