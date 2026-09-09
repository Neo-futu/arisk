<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# 当前系统菜单与全部子菜单

本文档描述 arisk 当前前端系统中实际定义的侧边栏菜单结构。

判定口径：

1. 以 `frontend/src/components/Sidebar/AppSidebar.tsx` 中的菜单定义为准。
2. 实际用户可见菜单，还会受到 `my-access-context` 返回的 `menu_paths` 与 `menu_stages` 过滤。
3. 超级管理员可预览除 `HIDDEN` 之外的菜单；普通用户只能看到已授权路径。
4. `1_datastorage/postgres/schema/011_user_menu.sql` 中的 `fsi.para_menu` 属于另一套历史/数据侧菜单配置，不等同于当前 React 侧边栏。

## 一、业务菜单（FSI Section）

| 一级菜单 | 路径 | 子菜单 | 子菜单路径 | 说明 |
|---|---|---|---|---|
| 仪表板 | `/` | - | - | 系统首页 |
| 组合驾驶舱 | `/portfolio-cockpit` | - | - | 组合总览与驾驶舱 |
| 投资风险分析 | `/investment-risk` | 模块总览 | `/investment-risk` | 父级菜单点击展开；子菜单入口与父路径相同 |
| 投资风险分析 | `/investment-risk` | 指标验证 | `/investment-risk/validation` |  |
| 投资风险分析 | `/investment-risk` | 组合概况 | `/investment-risk/overview` |  |
| 投资风险分析 | `/investment-risk` | 风险指标 | `/investment-risk/indicators` |  |
| 投资风险分析 | `/investment-risk` | 绩效归因 | `/investment-risk/attribution` |  |
| 投资风险分析 | `/investment-risk` | 利率与信用敏感度 | `/investment-risk/rates-credit` |  |
| 投资风险分析 | `/investment-risk` | 流动性与压力测试 | `/investment-risk/liquidity-stress` |  |
| 投资风险分析 | `/investment-risk` | 风险预算与前置试算 | `/investment-risk/pretrade-budget` |  |
| 投资风险分析 | `/investment-risk` | 宏观与市场动态 | `/investment-risk/macro-dynamics` |  |
| 投资风险分析 | `/investment-risk` | 基本面因子与行为 | `/investment-risk/factor-behavior` |  |
| 风险测试 | `/risk-testing` | 敏感度测试 | `/risk-testing/sensitivity` |  |
| 风险测试 | `/risk-testing` | 压力测试 | `/risk-testing/stress` |  |
| 风险测试 | `/risk-testing` | 情景测试 | `/risk-testing/scenario` |  |
| 风险测试 | `/risk-testing` | 反向压力测试 | `/risk-testing/reverse-stress` |  |
| 风险测试 | `/risk-testing` | 尾部风险测试 | `/risk-testing/tail-risk` |  |
| 风险测试 | `/risk-testing` | 关键利率久期 KRD | `/risk-testing/krd` |  |
| 风险测试 | `/risk-testing` | PnL 归因 | `/risk-testing/pnl-explain` |  |
| 风险测试 | `/risk-testing` | 历史收益回测 | `/risk-testing/historical-backtest` |  |
| 风险测试 | `/risk-testing` | VaR 回测 | `/risk-testing/var-backtest` |  |
| 风险测试 | `/risk-testing` | 估值调整 XVA | `/risk-testing/xva` |  |
| 数据管理中心 | `/data-management` | - | - | 业务数据维护工作台 |
| 指标探索 | `/indicator-explorer` | - | - | 指标数据检索与时序分析 |
| 持仓明细 | `/positions` | - | - | 组合持仓明细 |
| 组合估值与损益 | `/valuation` | - | - | 估值、损益与相关分析 |
| 组合优化 | `/portfolio-opt` | - | - | 投资组合优化 |
| 合规核查 | `/compliance` | - | - | 合规检查 |
| 风控规则配置 | `/risk-rules` | - | - | 风控规则维护 |
| 报表中心 | `/reports` | - | - | 报表查看与导出 |
| 定时任务 | `/schedules` | - | - | 定时作业配置与执行 |
| 自动风控 | `/autorisk` | - | - | 自动风控能力入口 |
| Agent Chat | `/chat` | - | - | 对话式 AI 能力入口 |
| 专家知识库 | `/expert` | - | - | 知识库与专业内容入口 |
| SQL 资产库 | `/sql-library` | - | - | SQL 资产与查询模板 |

## 二、系统管理菜单（System Management）

| 一级菜单 | 路径 | 子菜单 | 子菜单路径 | 说明 |
|---|---|---|---|---|
| 用户与权限管理 | `/admin` | - | - | 用户、角色、授权维护 |
| 系统配置 | `/system-config` | - | - | 发布阶段、菜单状态等配置 |
| API Key 管理 | `/api-keys` | - | - | 用户 API Key 管理 |
| 通知中心 | `/notifications` | - | - | 通知渠道与消息入口 |
| 设置 | `/settings` | - | - | 个人与系统设置 |

## 三、当前菜单树

```text
阿雷斯 · 智能风控和投资分析系统
├── 仪表板 (/)
├── 组合驾驶舱 (/portfolio-cockpit)
├── 投资风险分析 (/investment-risk)
│   ├── 模块总览 (/investment-risk)
│   ├── 指标验证 (/investment-risk/validation)
│   ├── 组合概况 (/investment-risk/overview)
│   ├── 风险指标 (/investment-risk/indicators)
│   ├── 绩效归因 (/investment-risk/attribution)
│   ├── 利率与信用敏感度 (/investment-risk/rates-credit)
│   ├── 流动性与压力测试 (/investment-risk/liquidity-stress)
│   ├── 风险预算与前置试算 (/investment-risk/pretrade-budget)
│   ├── 宏观与市场动态 (/investment-risk/macro-dynamics)
│   └── 基本面因子与行为 (/investment-risk/factor-behavior)
├── 风险测试 (/risk-testing)
│   ├── 敏感度测试 (/risk-testing/sensitivity)
│   ├── 压力测试 (/risk-testing/stress)
│   ├── 情景测试 (/risk-testing/scenario)
│   ├── 反向压力测试 (/risk-testing/reverse-stress)
│   ├── 尾部风险测试 (/risk-testing/tail-risk)
│   ├── 关键利率久期 KRD (/risk-testing/krd)
│   ├── PnL 归因 (/risk-testing/pnl-explain)
│   ├── 历史收益回测 (/risk-testing/historical-backtest)
│   ├── VaR 回测 (/risk-testing/var-backtest)
│   └── 估值调整 XVA (/risk-testing/xva)
├── 数据管理中心 (/data-management)
├── 指标探索 (/indicator-explorer)
├── 持仓明细 (/positions)
├── 组合估值与损益 (/valuation)
├── 组合优化 (/portfolio-opt)
├── 合规核查 (/compliance)
├── 风控规则配置 (/risk-rules)
├── 报表中心 (/reports)
├── 定时任务 (/schedules)
├── 自动风控 (/autorisk)
├── Agent Chat (/chat)
├── 专家知识库 (/expert)
├── SQL 资产库 (/sql-library)
└── 系统管理
    ├── 用户与权限管理 (/admin)
    ├── 系统配置 (/system-config)
    ├── API Key 管理 (/api-keys)
    ├── 通知中心 (/notifications)
    └── 设置 (/settings)
```

## 四、菜单显示规则

当前前端的菜单显示逻辑如下：

1. 菜单定义来源：`getFsiItems()` 与 `getAdminItems()`。
2. 鉴权来源：`fsiApi.getMyAccessContext()`。
3. 过滤规则：
   - 普通用户：仅显示 `menu_paths` 中存在的路径。
   - 超级管理员：显示所有 `menu_stages != HIDDEN` 的路径。
4. 菜单分组：
   - 业务菜单显示在 `fsiSection`。
   - 管理菜单显示在 `systemManagement`。
5. 发布阶段：当 `menu_stages[path] === BETA` 时，前端会展示 `Beta` 标记。

## 五、源码依据

当前文档依据以下文件整理：

1. `frontend/src/components/Sidebar/AppSidebar.tsx`
2. `frontend/src/i18n/resources/zh-CN.ts`
3. `frontend/src/routeTree.gen.ts`
4. `1_datastorage/postgres/schema/011_user_menu.sql`
