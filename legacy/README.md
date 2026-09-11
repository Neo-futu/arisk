<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# legacy — 遗留模块登记

## 用途

登记**尚未迁移**至目标架构的模块与路径，供迁移 Wave 对照。本目录不含业务逻辑，不替代实际代码位置。

## 当前遗留权威路径

| 领域 | 路径 | 目标 |
|---|---|---|
| 风险计算工具 | `2_processing/tools/` | `3_riskengine/` |
| 技能资产 | `3_skills/` | `7_ai/skills/` |
| MCP | `4_mcp/` | `5_integrations/mcp/` |
| 用户 Agent | `aiagent/` | `7_ai/agents/` |
| 平台 Agent | `platform_agent/` | `7_ai/agents/` |
| 自动风控 | `autorisk/` | Risk Workflow / `7_ai/workflows/` |

## 原则

- Old 路径在迁移完成前保持权威
- 不在 Wave 2 删除或批量重命名
