# 5_deploy — 部署編排層

## 模塊定位

FSI 風控業績平台六層架構的**第五層**，是平台的**Agent 定義與部署中樞**。負責定義 Agent 的能力邊界（技能/工具/子 Agent 組合）、人工審核規則，以及 Docker / Kubernetes 生產部署配置。

```
6_entry (觸發)
    ↓
【5_deploy】  ← 本層（Agent 定義 + 部署配置）
    ├── agents/      Agent YAML 定義
    ├── orchestrate.py  Orchestrator 事件循環
    ├── k8s/         Kubernetes 部署清單
    ├── docker/      Dockerfile
    └── scripts/     部署腳本
        ↓
3_skills + 4_mcp + 2_processing
```

---

## 目錄結構

```
5_deploy/
├── orchestrate.py              Orchestrator — Agent 事件循環主程序
├── agents/
│   ├── risk-agent/
│   │   ├── agent.yaml          風控分析 Agent 定義
│   │   └── subagents/
│   │       ├── data-puller.yaml    子 Agent：數據拉取（只讀）
│   │       ├── risk-calculator.yaml 子 Agent：風控計算（只讀）
│   │       └── report-writer.yaml  子 Agent：報告生成（write-holder）
│   └── compliance-agent/
│       └── agent.yaml          合規監控 Agent 定義
├── k8s/
│   └── deployment.yaml         Kubernetes 部署清單
├── docker/
│   └── Dockerfile.processing   Processing 服務 Docker 鏡像
└── scripts/
    └── deploy-agent.sh         Agent 部署腳本
```

---

## Agent 定義

### `risk-agent` — 風控分析 Agent

**職責：** 自主完成「持倉拉取 → 暴露計算 → VaR → MMF合規核查 → 報告生成」全流程

**技能載入：**
- `risk-analysis` SKILL — WAM/WAL/VaR/合規
- `mmf-compliance` SKILL — SFC 守則第8.2章核查
- `xlsx-report` SKILL — Excel 報表生成

**子 Agent 架構（分工明確）：**

| 子 Agent | 權限 | 職責 |
|---|---|---|
| `data-puller` | 只讀 | 從 Processing API 和 MCP 拉取持倉和市場數據 |
| `risk-calculator` | 只讀計算 | 執行暴露/VaR/WAM/WAL 計算 |
| `report-writer` | **write-holder** | 生成格式化報告（唯一有寫權限的子 Agent） |

**MCP 工具訪問：**
- `fsi-gateway` — 統一數據訪問
- `internal-db` — 內部 DB 只讀查詢

**人工審核觸發規則：**

```yaml
review_gates:
  - gate: pre_report_write      # 報告寫入前必須審核
    trigger: always
    category: REPORT_PUBLISH
    sla_minutes: 120

  - gate: compliance_breach     # SFC守則任何違規
    trigger: breach_flags_nonempty
    category: COMPLIANCE_BREACH
    sla_minutes: 30

  - gate: high_risk             # VaR > 5% NAV
    trigger: var_pct_nav_gt_5
    category: HIGH_RISK
    sla_minutes: 30
```

---

### `compliance-agent` — 合規監控 Agent

**職責：** 主動監控所有 MMF 組合的 SFC 守則合規狀態，發現違規立即觸發審核流程

---

## Orchestrator（`orchestrate.py`）

**核心事件循環：**

```
orchestrator
    ↓ 調用 data-puller（只讀）
    ↓ 調用 risk-calculator（只讀計算）
    ↓ [人工審核點 ①] — 如有 breach_flags（30分鐘SLA）
    ↓ 調用 report-writer（write-holder）
    ↓ [人工審核點 ②] — 報告發布前（120分鐘SLA）
    ↓ 完成，返回 artefact 路徑
```

**技術細節：**
- 使用 `anthropic` SDK 的 Managed Agent 模式
- 通過 `httpx` 調用 `2_processing` API
- 子 Agent 交接時插入 `checkpoint.block()` 阻塞點
- 所有操作記錄到 `svc_sys_op_log`

---

## 部署配置

### Docker（`Dockerfile.processing`）

```dockerfile
# Processing 服務鏡像
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[dev]"
CMD ["uvicorn", "2_processing.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Kubernetes（`deployment.yaml`）

包含：
- `processing-api` Deployment（`2_processing` FastAPI 服務）
- `celery-worker` Deployment（Celery 計算任務）
- `celery-beat` Deployment（定時任務調度）
- ConfigMap（環境變量）
- Service（內部服務發現）

### 部署腳本（`deploy-agent.sh`）

```bash
# 部署 Agent Bundle（同步 3_skills 技能到 Agent 目錄）
python scripts/sync_skills.py

# 部署到 k8s
kubectl apply -f k8s/deployment.yaml
```

---

## Agent 模式 vs Direct Query 模式

| 模式 | 適用場景 | 延遲 | 靈活性 |
|---|---|---|---|
| **Agent 模式** | 複雜分析、需要推理、多步驟 | 較高（秒級） | 高（可自主決策） |
| **Direct Query** | 標準報表、確定性查詢 | 低（毫秒級） | 低（固定流程） |

`6_entry` 層根據請求類型自動路由：`/agent/*` → Agent 模式；`/query/*` → Direct Query。

---

## 安全設計

- **write-holder 模式**：只有被明確指定為 `write-holder` 的子 Agent（`report-writer`）才能寫入文件或數據庫，其他子 Agent 只讀
- **人工審核閘門**：合規違規和高風險操作必須通過人工審核才能繼續，不可被 Agent 自行繞過
- **安全等級標記**：`security_tier: "internal"`，數據敏感度：`"confidential"`
- **審計追蹤**：所有 Agent 操作記錄到 `svc_wf_audit_log`

---

## 快速部署

```bash
# 本地開發
python 5_deploy/orchestrate.py --fund BHMMF --date 2026-06-25

# 同步技能（修改 SKILL.md 後執行）
python scripts/sync_skills.py

# 生產部署
kubectl apply -f 5_deploy/k8s/deployment.yaml
```
