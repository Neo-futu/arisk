# aiagent 編排層開發指南

本文件說明如何在 aiagent 內開發和擴展編排層（Orchestration）。

## 1. 編排層責任

編排層負責流程控制，不負責具體業務計算：

- 路由：根據請求選擇合適 agent
- 協作：多 agent handoff 與執行鏈
- 狀態：任務狀態機、日誌、結果存儲
- 通訊：SSE 事件流封裝

當前實現文件：

- `aiagent/orchestrator/supervisor.py`：單 agent/多 agent 路由
- `aiagent/orchestrator/task_state.py`：Redis 任務狀態機
- `aiagent/engine/stream.py`：SSE 流、Planner/Reflector 整合點

## 2. 編排層設計邊界

請保持以下邊界：

- Tools 層做能力執行，編排層不直接寫業務 SQL
- 編排層不直接耦合具體 skill 文本格式
- 編排層只處理流程事件（start/plan/text/tool_call/tool_result/reflection/done）
- 錯誤必須轉為事件並可追蹤

## 3. 新增編排規則流程

### 3.1 新增路由規則

編輯 `supervisor.py`：

- `_ROUTING_RULES`：新增意圖 -> agent_id 規則
- `_MULTI_AGENT_TRIGGERS`：新增多 agent 協作鏈

要求：

- 規則從精確到寬泛
- 嚴禁覆蓋用戶明確指定的 agent
- handoff 必須有上限，防止循環

### 3.2 新增狀態機節點

編輯 `task_state.py`：

- 在 `TaskStatus` 擴展狀態
- 在提交端點與 worker 流程補齊 transition
- 保證每個錯誤路徑都有 fail/cancel 狀態

建議：

- 任務狀態 key 保留 24h
- 任務結果 key 保留 7d

### 3.3 新增 SSE 事件

編輯 `stream.py`：

- 保持 `type` 字段穩定，不隨意改名
- 新事件向前兼容前端（未識別事件應可忽略）
- `error` 事件後必須結束為 `done`

## 4. 典型擴展模式

### 模式 A：複合任務多 agent 鏈

- `risk-analyst -> compliance-officer -> fund-reporter`
- 每次 handoff 將上一步摘要注入下一步上下文

### 模式 B：異步長任務

- 提交後立即返回 `task_id`
- 由 Celery/worker 更新狀態與結果
- 前端輪詢 task 狀態端點

## 5. 測試清單

每次調整編排層，至少驗證：

- 單 agent 對話可正常完成
- 多 agent handoff 可正常停止並返回 `done`
- Redis 不可用時可降級而不崩潰
- `error` 路徑會正確落盤狀態
- SSE 事件順序對前端可消費

## 6. 與其他層關係

- aiagent 編排層是 aiagent 自己的 runtime，不應承擔 3_skills 的獨立執行責任
- 3_skills 若作為獨立 agent，應由自己的 orchestrator/runtime 管理
- platform_agent 同理，應有獨立 orchestrator，不與 aiagent 狀態機混用
