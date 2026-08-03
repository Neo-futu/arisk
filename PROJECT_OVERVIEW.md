# ARISK — Agent for Risk & Investment Analysis System

> 版本：1.0.0 · 最後更新：2026-07-07

---

## 一、項目概述

ARISK 平台（Agent for Risk & Investment Analysis System）是一個面向香港認可基金（以貨幣市場基金為核心場景）的數據監控與風險分析平台。系統命名靈感源自航海飛行雷達，旨在為投資組合的日常風險度量提供客觀、精確的數據導航。

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

## 投資風險模塊

本模塊旨在將 ARISK 平台的覆蓋範圍由「中後台合規與操作風控」延伸至「前中台投資決策輔助與主動風險管理」。模塊深度融合量化定價模型與情景分析引擎，為基金經理（PM）與風險管理團隊提供動態的組合風險視角。

1. 核心功能矩陣
1.1 收益歸因與績效拆解 (Performance Attribution)

固收多因子歸因： 針對貨幣及短債基金，將組合超額收益精確拆解為：票息攜帶收益 (Carry)、收益曲線平行移動 (Curve Level Shift)、曲線扭曲/陡峭化 (Slope/Twist)、信用利差變動 (Spread Effect) 及特定券種選擇效應 (Selection)。

Brinson-Fachler 擴展： 支援多資產組合的資產配置效應 (Allocation) 與標的選擇效應 (Selection) 評估，精準定位超額收益來源。

1.2 利率與信用風險敏感度 (Rates & Credit Sensitivities)

關鍵期限久期 (Key Rate Duration, KRD)： 計算組合在 1M, 3M, 6M, 1Y 等關鍵節點的久期暴露，精準捕捉收益曲線非平行移動風險。

信用利差敏感度 (CS01 / Spread DV01)： 量化信用利差每變動 1 個基點（bps）對基金淨值（NAV）的絕對影響。

信用遷移與集中度穿透： 實時監測穿透至底層發行人（Issuer）的集中度及 HHI 指數（Herfindahl-Hirschman Index），提供評級下調（Downgrade Migration）的潛在敞口預警。

1.3 流動性風險與壓力測試 (Liquidity & Stress Testing)

資產變現天數 (Time-to-Liquidate, TTL)： 結合市場日均交易量 (ADV) 與買賣價差，計算在無重大市場衝擊下變現特定比例資產所需的時間，科學劃分 L1-L4 流動性資產池。

多情景壓力測試 (Stress Testing)：

歷史情景： 模擬 2008 金融危機、2020 年 3 月流動性緊縮等極端市場下的淨值回撤。

假設情景 (Redemption Shock)： 模擬單一或多個大客戶突發 20%-30% 大額贖回對流動性資產覆蓋率及 WAM/WAL 的衝擊。

反向壓力測試 (Reverse Stress Testing)： 測算導致組合觸發 SFC 監管紅線或淨值跌破面值所需的最小宏觀變量衝擊。

1.4 風險預算與前置試算 (Risk Budgeting & Pre-trade Analysis)

邊際風險貢獻 (MCTR)： 量化單一資產或策略對組合整體 VaR 或波動率的邊際貢獻，輔助優化頭寸。

事前交易校驗 (Pre-trade Risk Check)： 在新訂單執行前，模擬其對 WAM、WAL、集中度及跟蹤誤差（Tracking Error）的影響，防止被動越權。

1.5 宏觀與市場動態風險 (Macro & Market Dynamics Risk)

宏觀經濟與週期指標： 建立宏觀數據監控矩陣（涵蓋 PMI、CPI/PPI、非農就業、央行基準利率預期等）。透過隱含波動率與宏觀數據的關聯分析，評估宏觀狀態轉換（Regime Shift）對不同資產類別與行業板塊定價的系統性衝擊。

跨市場關聯度與傳染風險 (Contagion Risk)： 監控全球主要大類資產（如美債收益率曲線、美元指數、VIX 指數、信用利差等）的跨資產相關性矩陣變化，識別極端市場環境下的相關性破裂或風險傳染路徑。

1.6 基本面、因子與行為風險 (Fundamental, Factor & Behavioral Risk)

基本面與財務健康度分析： 穿透至底層發行人或上市公司的基本面數據。對於固收資產，監控利息保障倍數、資產負債率等償債能力指標；對於權益類資產，監控盈利質量與估值水位，防範基本面惡化導致的估值殺跌（Value Trap）或信用違約。

因子暴露與投資偏好 (Factor & Style Exposure)： 基於多因子模型（如 Barra 模型），量化投資組合在規模（Size）、價值（Value）、動量（Momentum）、質量（Quality）、低波動（Low Volatility）等風格因子上的敞口，監測非預期的風格漂移（Style Drift）。

市場微觀結構與交易擁擠度 (Trading Crowding)：

擁擠度指標構建： 綜合換手率、資金淨流入、融資融券餘額、期權看跌/看漲比例（Put/Call Ratio）等市場微觀數據，構建行業板塊及特定因子的擁擠度評分。

踩踏風險預警： 當某一板塊或策略的交易擁擠度達到歷史極值區域時，系統自動觸發預警，防範因流動性枯竭或趨勢反轉引發的踩踏拋售效應（Stampede Effect）。

2. 系統架構整合與數據流
投資風險模塊完全融入現有的六層解耦架構中，採用非同步計算與 Agent 智能調度相結合的模式：

2_processing（計算引擎層）： 新增投資風險專屬 FastAPI 路由（如 /api/v1/inv-risk/krd、/api/v1/inv-risk/stress-test）

1_datastorage（存儲層）： 在 fsi schema 下擴充 portfolio_sensitivities（敏感度快照）、stress_test_results（壓測結果）等時序表，支援高效的歷史風險數據回溯。

5_deploy & 4_mcp（Agent 擴展層）： 部署專屬的 InvestmentRisk Subagent。透過 MCP 接口，允許使用者以自然語言下達複雜指令（例：「以 2022 年美聯儲連續加息為情景，測算當前組合若遭遇 15% 贖回時的流動性缺口」），系統將自動編排底層計算工具並輸出結構化風險報告。



