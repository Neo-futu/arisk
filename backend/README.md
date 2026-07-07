# ARISK Backend

根目錄 `backend/` 是對外 Web API 層，負責 JWT 認證和 FSI 路由統一代理。

## 職責

- 對前端暴露 `/api/v1/*`
- 代理 FSI 風控與持倉到 `2_processing`
- 代理 Agent/Chat 能力到 `6_entry`

## 依賴

- Python 3.12+
- `uv`（推薦）

安裝：

```bash
cd backend
uv sync
```

## 本地啟動

在根目錄設置必要環境變量後啟動：

```powershell
$env:ENTRY_API_URL='http://127.0.0.1:8010'
$env:PROCESSING_API_URL='http://127.0.0.1:8001'
$env:PROCESSING_API_KEY='internal_key_change_me'

cd backend
fastapi dev app/main.py --host 127.0.0.1 --port 8000
```

文檔地址：`http://localhost:8000/docs`

## 與其他服務的關係

- 上游：`frontend/`
- 下游：`2_processing/`、`6_entry/`

## 主要路由入口

- 路由聚合：`backend/app/api/main.py`
- FSI 代理：`backend/app/api/routes/fsi/`
- 配置：`backend/app/core/config.py`

## 推薦一鍵啟動

倉庫根目錄：

```bash
python scripts/dev.py --profile web
```

Windows PowerShell：

```powershell
./scripts/dev.ps1 -Profile web
```
