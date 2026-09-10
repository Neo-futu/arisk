<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# ARISK Platform V2 Final Validation Report

结论：**NOT READY**。

本报告只记录 2026-09-09 本机实际运行结果。未通过的套件不得标 READY。

## 1. Architecture

ARISK 当前形态为机构投资与风险平台：Market Data → Portfolio/Position → Valuation → Investment Risk → Portfolio Optimization → Simulation → Risk Testing → Limits → Pre-Trade → Trading → Position → Valuation → Continuous Risk。

计算权威在 `3_riskengine/`；业务编排在 `4_business/`；外部系统经 `5_integrations/`；自然语言入口在 `7_ai/`（Chat 运行时仍为 `aiagent/`，MCP 运行时仍为 `4_mcp/`）。Frontend 不承担金融计算。

实测：`3_riskengine/tests` + `2_processing/test` **259 passed**；机构链路 `test_institutional_business_chain` 通过。

## 2. Business Modules

| 模块 | 实测 |
|---|---|
| Investment Risk Analysis | 14 域 KPI pack 通过；`GET /investment/kpi-catalog` 200 |
| Portfolio Construction & Optimization | 9 种方法权重归一；闸门 `optimize_and_govern` 通过；`GET /portfolio-opt/catalog` 200 |
| Risk Testing | 10 项 analytic 在样例快照上执行通过；`GET /risk-testing/catalog` 200（修复 `scenario_catalog` 导入后） |
| Trading / Pre-Trade / Operations | 样例单 `APPROVE` → `ACCEPTED_SIM`；非交易指令 |

## 3. RiskEngine

`RiskEngine.bind(sample_snapshot)` 实测通过：Valuation / Risk / Stress / Scenario / Liquidity / Counterparty / PnL / Limits / Validation。FinancePy Adapter `available=true`。Riskfolio / ORE Adapter 可初始化，运行时库缺失时走既定 fallback。

## 4. FinancePy

- 安装包：`financepy==1.1.2`（`site-packages`，非工作树源码）
- Adapter 可用；贴现因子与估值回归通过
- 第三方源码目录 `FinancePy/` 在 `.gitignore`；补丁日志无修改

## 5. Riskfolio-Lib

- `import riskfolio`：**失败**（`ModuleNotFoundError`）
- Adapter `available=false`；优化走 RiskEngine numpy fallback
- 补丁日志无修改；版本：未安装

## 6. ORE

- `import QuantLib`：**失败**
- ORE Adapter `available=false`；XVA/复杂衍生品走 RiskEngine 确定性路径
- 补丁日志无修改；版本：未安装

## 7. Data

`1_datastorage/postgres/schema` 解析 **104** 张 `fsi.*` 表，表名无重复。权威主数据：

| 域 | 权威表 |
|---|---|
| Market | `fsi.mktdata_*` |
| Portfolio | `fsi.para_portfolio` |
| Position | `fsi.balance_*` |
| Trade | `fsi.transact_*` |
| Valuation | `fsi.balance_valuation_sheet` |
| NAV | `fsi.balance_portfolio_nav` |
| PnL | `fsi.transact_portfolio_pnl` |
| Risk | `fsi.svc_risk_snapshot` |

KPI `data_quality.source_tables` 为 `fsi.balance_*` / `fsi.mktdata_*`。`5_integrations` 合同不是第二套持仓主数据。

## 8. Valuation

样例组合 `TEST001`（NAV 1,000,000 HKD）`price()` PV = 1,000,000；利率冲击 PnL < 0。耗时 **5.702 ms**。

## 9. Risk

Sensitivity / Exposure / 21 KPI 通过。VaR 经 Quant REST `POST /quant/risk/var` 返回 `kpi=VaR`。耗时 **6.415 ms**。

## 10. Stress

GFC 2008 情景 `analytic=STRESS` 通过。耗时 **4.993 ms**。

## 11. Portfolio Optimization

HRP `optimize_and_govern` 通过；`is_trade_instruction=false`。耗时 **126.180 ms**。Simulation clone / stress / compare 通过。

## 12. Governance

统一 Limit Engine：样例快照 `GREEN`。Pre-Trade 样例 `APPROVE`。HARD_BREACH 不可例外（既有 Wave 6 测试仍绿）。JWT / Role / Portfolio / API / Audit 闸门：Agent 内核测试通过。

## 13. API

Processing：`/health` 200；无 `X-API-Key` 访问 `/quant/catalog` **403**；Quant / Agents / Limits / Pre-Trade / KPI catalog / Risk Testing catalog / Portfolio-Opt catalog 200。Agent `apply live` + `viewer` **403**。

Backend JWT 登录在本机 Postgres `fsi_risk` 上部分通过：`POST /api/v1/login/access-token` 200。`backend/tests/api` **47 passed / 7 failed**（见 §18）。

## 14. Frontend

- `tsc -p tsconfig.build.json --noEmit` 通过
- Playwright `chromium-menu`（`menu-architecture.spec.ts`）**5 passed**：Sidebar、Permission、Deep Link、Refresh、Beta、HIDDEN
- 深链 `/investment-risk/overview#asset-risk` 在无持仓数据时仍保留锚点（否则 E2E 找不到 `#asset-risk`）
- 依赖登录的 Playwright 项目（`login` / `items` / `setup`）**未作为全绿套件跑完**（需完整 auth setup）

## 15. Agent

`7_ai.run("portfolio VaR")` 经 Tool → RiskEngine，`ok=true`。MCP `connect(Risk, calculate=VaR)` 返回 `MCP_NOT_ENGINE`。Chat 路径 `/api/v1/fsi/agent` 与 `aiagent/` 仍在。AutoRisk **13 passed**。

## 16. Integration

`5_integrations` Market Data / PMS / OMS / EMS / Broker / Custodian / Fund Admin / Accounting / Quant 既有 Wave 7 测试仍绿。外部 → Adapter → Data Contract → RiskEngine 链路在样例上通过。

## 17. Security

通过：Processing API key、Agent JWT/Role/Portfolio/Tool、OMS 未授权拒绝（既有测试）、HARD_BREACH 锁定。

未通过 / 未闭环：Backend 若干权限文案断言、邮件模板缺失、JWT HMAC 密钥长度警告（20 bytes < 32）。Redis 连接超时。

## 18. Regression

必须保持的面：MMF 脚本仍在 `2_processing/tools/mmf/`；Data Management / Cockpit / Positions / Valuation / Reports / Schedules / AutoRisk / Agent / MCP / Compliance / Risk Rules / Auth / Audit / Human Review 模块可导入，Processing 路由前缀齐全。

`2_processing/test` + `3_riskengine/tests`：**259 passed**。AutoRisk：**13 passed**。Backend API：**47 passed, 7 failed**（邮件模板、菜单 BETA/GA 与库内现状不符、重复 email、权限文案）。

## 19. Performance

样例快照本机探测（2026-09-09）：

| 指标 | 结果 |
|---|---|
| Valuation Time | 5.702 ms |
| Risk Calculation Time | 6.415 ms |
| Stress Time | 4.993 ms |
| Optimization Time | 126.180 ms |
| API Latency `/health` | 0.761 ms |
| API Latency `/quant/catalog` | 2.597 ms |
| Database Query `SELECT 1` | 69.497 ms |
| Memory (tracemalloc peak) | 129.7 KiB（该探针窗口） |
| Background Jobs（报表调度线程） | alive |
| Redis | **TimeoutError** |

## 20. Technical Debt

- `3_riskengine/{stress,scenario,liquidity,counterparty,pnl}` 仍为 skeleton；实现在 `risk` / `kpis` / `2_processing/tools/risk_testing`
- Riskfolio-Lib / QuantLib / ORE 未装入本机运行时
- Redis 未就绪（人工审核等路径依赖）
- Backend 测试与开发库状态、邮件模板、权限文案不一致
- JWT 签名密钥短于 RFC 建议

## 21. Remaining Work

1. 安装并回归 Riskfolio-Lib、QuantLib/ORE（或明确生产降级策略并写入运行手册）
2. 启动 Redis，重跑审核 / 缓存 / 作业路径
3. 修复 Backend 测试与种子数据：菜单 `release_stage`、用户 email 唯一、`email-templates/build`
4. 跑通带登录的 Playwright 全套（`setup` + `chromium`）
5. 将限额 / 估值 / 优化从样例快照扩展到真实 `fsi.balance_*` 基金日终作业
6. 收紧 JWT 密钥长度

## 22. Production Readiness

**NOT READY**

阻止项：Riskfolio-Lib 与 ORE 运行时缺失；Redis 不可用；Backend API 测试未全绿；登录态 Frontend E2E 未全绿。机构链路与 RiskEngine 样例计算已实测通过，但不能替代上述运行时与回归缺口。
