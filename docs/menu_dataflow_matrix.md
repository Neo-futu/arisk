# 全菜單數據流對照清單

目的：把前端菜單功能映射到 Backend 路由、Processing 計算入口、以及主要數據源（DB/文件），便於逐項聯調與驗證。

來源基準：
- 菜單定義：frontend/src/components/Sidebar/AppSidebar.tsx
- FSI 路由聚合：backend/app/api/routes/fsi/router.py
- Processing 路由聚合：2_processing/api/main.py

## 1) FSI 業務菜單（主工作流）

| 菜單功能 | 前端主要調用 | Backend 路由 | Processing 入口函數 | 主要數據源（DB/文件） | 單元驗證要點 |
|---|---|---|---|---|---|
| 儀表板 / | fsiApi.getExposureLatestDate, fsiApi.getExposure | /api/v1/fsi/risk/exposure-latest-date/{fund_id}, /api/v1/fsi/risk/exposure/{fund_id} | find_latest_exposure_date, compute_exposure | fsi.balance_portfolio_nav, fsi.balance_portfolio_mmf, fsi.balance_portfolio_asset, fsi.balance_bond, fsi.balance_cd, fsi.balance_deposit, fsi.balance_repo, fsi.balance_cash | latest-date 返回 effective_date；exposure 返回 total_nav_hkd > 0、WAM/WAL/流動性與 breach_flags |
| 投資風險分析 / 模塊總覽 | fsiApi.getPortfolioOverview（帶前端 fallback） | /api/v1/fsi/investment/overview/{fund_id} | compute_portfolio_overview | fsi.para_portfolio, fsi.balance_portfolio_nav, fsi.balance_portfolio_asset, fsi.balance_stock | 檢查 portfolio.data_date、asset_allocation、top_stocks |
| 投資風險分析 / 組合概況 | fsiApi.getPortfolioOverview, fsiApi.getPortfolioOverviewTimeseries | /api/v1/fsi/investment/overview/{fund_id}, /api/v1/fsi/investment/overview-timeseries/{fund_id} | compute_portfolio_overview, compute_portfolio_overview_timeseries | 同上 + fsi.balance_portfolio_nav 時序 | 點位 points 非空，cumulative_return_pct 合理連續 |
| 投資風險分析 / 風險指標 | fsiApi.getRiskIndicators, fsiApi.getRiskIndicatorTimeseries, fsiApi.getVarCompare | /api/v1/fsi/investment/risk-indicators/{fund_id}, /api/v1/fsi/investment/risk-indicators-timeseries/{fund_id}, /api/v1/fsi/risk/var-compare/{fund_id} | compute_risk_indicators, compute_risk_indicator_timeseries, compute_historical_var/compute_monte_carlo_var/compute_distribution_var | fsi.balance_portfolio_nav, fsi.transact_stock, fsi.balance_stock, fsi.nav_history, fsi.raw_nav | 三方法 VaR 都有結果；時序含 drawdown/rolling_var |
| 投資風險分析 / 績效歸因 | fsiApi.getPerformanceAttribution, fsiApi.getPerformanceAttributionTimeseries | /api/v1/fsi/investment/attribution/{fund_id}, /api/v1/fsi/investment/attribution-timeseries/{fund_id} | compute_performance_attribution, compute_performance_attribution_timeseries | fsi.balance_stock, fsi.mktdata_quotes, fsi.mktdata_index_component, fsi.mktdata_stock_static, fsi.transact_pnl_item | 檢查 active return、pnl_points、Top 貢獻對齊 |
| 投資風險分析 / 利率與信用敏感度 | fsiApi.getRatesCredit | /api/v1/fsi/investment/rates-credit/{fund_id} | compute_rates_credit_sensitivity | fsi.balance_portfolio_nav, fsi.balance_bond | DV01/久期/評級分布字段完整 |
| 投資風險分析 / 流動性與壓力測試 | fsiApi.getLiquidityStress | /api/v1/fsi/investment/liquidity-stress/{fund_id} | compute_liquidity_stress_testing | fsi.balance_portfolio_nav, fsi.balance_portfolio_asset, fsi.balance_bond | redemption_pct、rate_shock_bps 參數生效，輸出含壓測結果 |
| 投資風險分析 / 風險預算與前置試算 | fsiApi.getPretradeCheck | /api/v1/fsi/investment/pretrade-check/{fund_id} | compute_pretrade_risk_budget | fsi.balance_portfolio_nav, fsi.balance_bond | BUY/SELL 邏輯、交易金額/久期敏感度變化 |
| 投資風險分析 / 宏觀與市場動態 | fsiApi.getMacroDynamics | /api/v1/fsi/investment/macro-dynamics/{fund_id} | compute_macro_market_dynamics | fsi.mktdata_index_quotes（及基準映射） | 輸出 regime/關聯分析字段 |
| 投資風險分析 / 基本面因子與行為 | fsiApi.getFactorBehavior | /api/v1/fsi/investment/factor-behavior/{fund_id} | compute_factor_behavior_risk | fsi.balance_stock, fsi.mktdata_quotes, fsi.transact_stock | 因子暴露、擁擠度、行為風險字段完整 |
| 持倉明細 | fsiApi.getPositions | /api/v1/fsi/positions/{fund_id} | get_positions（router 內 SQL） | fsi.positions（主）；fallback: fsi.balance_valuation_sheet | count 與 positions 長度一致；asset_type 過濾正確 |
| 合規核查 | fsiApi.getExposure | /api/v1/fsi/risk/exposure/{fund_id} | compute_exposure | 同儀表板 exposure 表集合 | 規則閾值與 breach_flags 一致 |
| 報表中心 | fsiApi.generateReport/getReportTask/getReportResult/downloadReport | /api/v1/fsi/reports/generate, /tasks/{task_id}, /result/{report_id}, /download/{report_id}/{filename} | 2_processing/api/routers/reports.py 中 _run_report_sync（腳本調度） | 文件：artefacts/reports, 2_processing/sql/mmf/output；底層由報表腳本查 fsi 業務表 | 任務狀態 queued→running→completed；可下載文件 |
| 定時任務 | fsiApi.listSchedules/create/update/delete/run-now/history/files/download | /api/v1/fsi/schedules/* | 2_processing/api/routers/schedules.py（JSON 持久化 + 調度線程） | 文件：artefacts/schedules.json, artefacts/schedules_history.json, artefacts/scheduled | 新建任務後可到點觸發；history 與 files 可回查 |
| 自動風控 | 外鏈 VITE_AUTORISK_URL（demo/docs/health） | N/A（當前頁面不經 backend） | N/A | autorisk 獨立服務（默認 8100） | /health 返回可用；demo 可打開 |

## 2) AI / 知識與系統管理菜單

| 菜單功能 | 前端主要調用 | Backend 路由 | Processing 入口函數 | 主要數據源（DB/文件） | 單元驗證要點 |
|---|---|---|---|---|---|
| Agent Chat | fsiApi.streamAgentChat, listAgents, listModels, listChatSessions, getChatMessages, saveChatMessages, getMyAgentConfig, refreshSkills | /api/v1/fsi/agent/v2/*, /api/v1/chat/*, /api/v1/agent-config/me, /api/v1/knowledge/refresh-skills | FSI Agent 由 backend 轉發至 6_entry；非 processing 直算 | DB: chatdb.chat_session, chatdb.chat_message, iam.user_agent_config；知識：chatdb.knowledge_document/chatdb.knowledge_chunk | SSE 有 text/tool_call/tool_result/done；會話可持久化回放 |
| 專家知識庫 | fsiApi.listModels + axios 調 /api/v1/knowledge/* | /api/v1/knowledge/ingest, ingest-file, extract-skill, save-skill, refresh-skills, documents, delete | N/A（backend + aiagent memory） | DB: chatdb.knowledge_document, chatdb.knowledge_chunk；文件：3_skills/skills 或 aiagent/skills | 提取技能後可保存並在 documents 看到 chunk_count |
| 用戶管理（超管） | UsersService.readUsers/create/update/delete/readUserMe | /api/v1/users/* | N/A | DB: iam.user（及關聯 iam.user_role 等） | 分頁查詢、增刪改查、權限保護 |
| API Key 管理 | fsiApi.listApiKeys/getLocalApiConfig/createApiKey/revokeApiKey | /api/v1/api-keys/* | N/A | DB: iam.user_api_key | 新建只返回一次明文 key；revoke 後不可再用 |
| 通知中心 | fsiApi.getNotificationChannels/sendNotification | /api/v1/notifications/channels, /email, /feishu, /wecom | N/A | 配置與外部通道：SMTP、FEISHU_WEBHOOK_URL、WECOM_WEBHOOK_URL | channel configured 狀態正確；發送返回 sent |
| 設置 | UsersService.updateUserMe/updatePasswordMe/deleteUserMe | /api/v1/users/me, /api/v1/users/me/password, /api/v1/users/me | N/A | DB: iam.user | 修改個人資料/密碼/註銷流程完整 |

## 3) 每個數據單元最小驗證模板

按下面模板為每個端點建測試 case（Postman 或 pytest + httpx 均可）：

1. 請求輸入驗證
- 必填參數缺失（fund_id、日期、區間）
- 邊界參數（start > end、超長區間、trade_side 非法）

2. 響應結構驗證
- HTTP 狀態碼
- JSON 結構完整（字段存在、類型正確）
- 關鍵數值非空（如 total_nav_hkd、points、count）

3. 口徑一致性驗證
- 同一 fund_id/as_of_date 在不同頁口徑一致（例如 NAV、return）
- 回退日期 effective_date 與展示日期一致

4. 可追蹤性驗證
- 記錄請求參數 + 返回摘要 + 上游來源（backend route / processing function / DB table）
- 異常時保留錯誤 detail，定位到具體層

## 4) 推薦聯調順序

1. 儀表板 exposure 鏈路（最短核心鏈）
2. 持倉明細 + 合規核查（共享多張 fsi 表）
3. 投資風險分析 8 個子頁（overview -> indicators -> attribution -> 其餘四頁）
4. 報表中心與定時任務（文件型輸出）
5. Agent Chat / 專家知識庫（SSE + 知識庫）
6. 系統管理（users/api-keys/notifications/settings）

## 5) 重要注意事項

- 報表中心與定時任務核心輸出是文件，驗證重點不是單一 JSON，而是任務狀態 + 文件存在性。
- 自動風控頁目前是外部服務入口，不走 backend/proccessing；若要納入統一鏈路，需新增 backend 代理層。
- Agent Chat 的模型列表目前為 backend 靜態配置 + 6_entry 工具流，與 processing 計算域解耦。
