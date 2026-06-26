# FSI Risk Platform

六層架構的基金風控與業績分析平台，支援 Agent 模式與非 Agent 直接查詢模式。

## 項目架構（由下至上）

```
1_datastorage/     資料儲存層  — Postgres · TimescaleDB · Redis · S3
2_processing/      計算處理層  — ETL · 風控指標 · 業績分析 · FastAPI workers
3_skills/          能力技能層  — SKILL.md · commands · 共用 prompt 庫
4_mcp/             資料連接層  — WindAPI MCP · 內部 MCP gateway
5_deploy/          部署編排層  — agent.yaml · subagents · k8s · Docker
6_entry/           入口層     — Excel · Python CLI · Web UI · Direct API
```

## 開發規則

### 編輯原則
- **技能來源**：所有 SKILL.md 在 `3_skills/skills/` 修改，禁止直接改 agent bundle 副本
- **SQL 修改**：schema 變更走 `1_datastorage/postgres/migrations/`，不直接改 schema 文件
- **API 修改**：Processing API (`2_processing/api/`) 與 Entry Web API (`6_entry/web/`) 職責分離

### 運行檢查
```bash
python scripts/check.py        # lint + 跨層引用驗證
python scripts/sync_skills.py  # 將 3_skills/ 同步到各 agent bundle
```

### 環境設置
```bash
cp .env.example .env           # 填入實際 key
docker-compose -f 1_datastorage/docker-compose.yml up -d
pip install -e ".[dev]"
```

## 層間職責邊界

| 層 | 讀 | 寫 | 觸發方 |
|---|---|---|---|
| datastorage | processing, skills(只讀查詢) | processing ETL workers | processing |
| processing | datastorage, 4_mcp | datastorage | entry / deploy |
| skills | 透過 MCP 讀 processing API | xlsx artefact（由 write-holder subagent） | agent / entry |
| mcp | 外部 API, 內部 DB | — | processing, skills |
| deploy | 3_skills, 5_deploy configs | — | CI/CD |
| entry | processing API, skills | — | 使用者 |

## 四大場景

1. **Excel live** → `6_entry/excel/bootstrap` → `3_skills/` → `2_processing/api/`
2. **Python 腳本** → `6_entry/cli/run.py` → `2_processing/` → `1_datastorage/`
3. **Web chat UI** → `6_entry/web/app.py` → agent 或 direct skill
4. **Agent vs Direct** → `5_deploy/agents/` 或 `6_entry/api/direct/`
