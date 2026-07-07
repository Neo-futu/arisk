# ARISK — Agent for Risk & Investment Analysis System

> 版本：1.0.0 · 最後更新：2026-07-07

---

## 一、項目概述

COMPASS 平台（原 FSI Risk Platform）是一個面向香港認可基金（以貨幣市場基金為核心場景）的數據監控與風險分析平台。系統命名靈感源自香港交易所（中環交易廣場）標誌性的羅盤雕塑，旨在為投資組合的日常風險度量提供客觀、精確的數據導航。

平台定位為持牌業務的底層數據技術工具，不替代管理層的合規決策與日常運營責任。平台採用六層解耦架構，支援 Claude Agent 模式（複雜多步驟分析）與非 Agent 直接查詢模式（低延遲確定性計算），並內建雙軌校驗體系（小富 AI 審核 + 人工審核）與全鏈路操作日誌，確保全業務流程符合 SFC 對於「內部控制與清晰留痕（Audit Trail）」的審慎監管要求。

### 適用場景

**貨幣市場基金合規核查：** 嚴格對齊 SFC《單位信託及互惠基金守則》第 8.2 章合規指標。

**每日風控快照監控：** 實時加權平均到期日（WAM）、加權平均法律到期日（WAL）、風險暴露（Exposure）、風險價值（VaR）及流動性資產比例。

**業績歸因分析：** 基於精細化 Brinson-Fachler (BHB) 模型的組合業績歸因。

**持倉與集中度監控：** 穿透式持倉分析，防止發行人及交易對手方集中度超限。

**風險報告校驗與發布：** 自動化生成數據快照，並進入內置雙軌校驗流程。

---

## 二、系統核心架構與訪問模式

平台採用「分層能力平台 + 統一前後端產品入口」的六層架構設計，確保高並發環境下的數據準確性與系統穩定性，並提供以下多模態交互與訪問模式：

### 1. 雙軌驅動的訪問模式

**Claude Agent 模式（複雜多步驟分析）：** 針對投資限制漂移、市場極端異常變動或 OCF（經常性開支比率）偏離超限等複雜場景，由內置的 Agent 智能體自主調度底層工具鏈，執行深度推理並自動生成風險分析與安全防範建議。

**非 Agent 直接查詢模式（低延遲確定性計算）：** 面向量化策略、基金會計（FA）或監管日常調閱，提供高可用、零時延的標準化 API 和結構化數據直接查詢，確保風控指標與每日淨值（NAV）計提的絕對精確。

### 2. 多模態產品入口

**Web 門戶模式 (Standard Web)：** 提供直觀的風險儀表盤（Dashboard）、WAM/WAL 監控看板及合規紅線預警，用於中後台日常的高頻監控與數據流管理。

**Chat 交互模式 (Conversational Chat)：** 允許風控人員或高級管理層通過自然語言快速調取特定子基金的即時風險指標（如："當前子基金的 WAM 是否接近 8.2 章紅線？"）。

### 3. 雙軌校驗與安全體系

**雙軌校驗機制：** 所有核心風控報告與對外發布材料，必須通過「小富 AI 審核 + 人工審核」雙重校驗，最大程度減少人工手動操作的潛在錯誤，確保數據與業務系統安全。

**全鏈路操作日誌（Audit Trail）：** 系統對所有查詢、修改及審核流進行不可篡改的日誌留痕，全面迎合 SFC 現場檢查（On-site Inspection）時的管理層審查要求。

---

## 三、六層架構總覽（由下至上）

```
┌─────────────────────────────────────────────────────────────────────┐
│  frontend/        React 19 + Vite + shadcn/ui（Web UI）             │
│  backend/         FastAPI + JWT（Web API 認證層）                    │
├─────────────────────────────────────────────────────────────────────┤
│  6_entry/         Excel · Python CLI · Agent 模式 · Direct API      │
├─────────────────────────────────────────────────────────────────────┤
│  5_deploy/        Agent YAMLs · Subagents · Orchestrator · k8s      │
├─────────────────────────────────────────────────────────────────────┤
│  3_skills/        SKILL.md · Commands · Human-Review Skill          │
├─────────────────────────────────────────────────────────────────────┤
│  4_mcp/           WindAPI MCP · Internal DB MCP · Gateway           │
├─────────────────────────────────────────────────────────────────────┤
│  2_processing/    ETL · 風控計算引擎 · 業績歸因 · FastAPI (8001)    │
├─────────────────────────────────────────────────────────────────────┤
│  1_datastorage/   PostgreSQL · TimescaleDB · Redis · MinIO/S3       │
└─────────────────────────────────────────────────────────────────────┘
```

### 前後端分離數據流

```
瀏覽器 → frontend (Vite:5173)
       → /api/v1/fsi/* → backend (FastAPI:8000, JWT 認證)
       ├── /risk/* /positions/* → 2_processing (FastAPI:8001)
       └── /agent/* → 6_entry (FastAPI:8010)
       → PostgreSQL fsi schema
```

---

## 四、本地開發啟動

**前置條件（本機安裝，無需 Docker）：**

| 組件 | 版本 | 說明 |
|---|---|---|
| PostgreSQL | 16+ | 主數據庫 |
| Redis | 7+ | Celery broker + 緩存 |
| Python | 3.12+ | 後端 + Processing |
| uv | latest | Python 包管理器 |
| Bun / Node | 20+ | 前端開發 |

**首次初始化：**

```bash
# 1. 配置環境
copy .env.example .env  # 填入 POSTGRES_PASSWORD / SECRET_KEY

# 2. 建庫 + FSI Schema
python scripts/setup_db.py

# 3. 安裝依賴
cd backend && uv sync && cd ..
pip install -r 2_processing/requirements.txt

# 4. Auth 表 + 超管用戶
cd backend && alembic upgrade head && python app/initial_data.py && cd ..

# 5. 前端依賴
cd frontend && bun install && cd ..
```

**日常啟動（一條命令）：**

```bash
python scripts/dev.py
```

| 服務 | 端口 | 說明 |
|---|---|---|
| frontend | 5173 | React SPA |
| backend | 8000 | Web API + 文檔 /docs |
| 6_entry | 8010 | Agent/Direct 內部入口 |
| processing | 8001 | 計算引擎 + 文檔 /docs |

---

## 五、技術棧

| 層 | 技術 |
|---|---|
| Web UI | React 19 · TypeScript · Vite · TanStack Router · React Query · shadcn/ui · Tailwind CSS |
| Web API | FastAPI · SQLModel · Alembic · JWT (PyJWT + pwdlib) · httpx |
| 計算引擎 | FastAPI · SQLAlchemy (async) · asyncpg · Celery · pandas · numpy · scipy |
| AI / Agent | Anthropic Claude API (claude-sonnet-4-6) · MCP Protocol |
| 數據庫 | PostgreSQL 16 · TimescaleDB · Redis 7 |
| 報表生成 | openpyxl · reportlab · python-docx · matplotlib |
