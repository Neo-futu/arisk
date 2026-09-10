<!-- 更新时间：2026-09-09（北京时间）｜生成模型：Cursor Grok 4.6 -->

# 第三方源码边界与补丁记录

## 边界

| 类别 | 路径 | 运行时角色 |
|---|---|---|
| 第三方源码（本地工作树，`.gitignore`） | `FinancePy/`、`Riskfolio-Lib/`、`ORE/` | 参考源码；**不是** Git 可复现依赖 |
| 第三方运行时 | 已安装的 `financepy`；`QuantLib`；`ORE`（ORE-SWIG，`site-packages/ORE`） | FinancePy Adapter；ORE Adapter 定价 / XVA 内核 |
| ARISK 自有源码 | `3_riskengine/`、`4_business/`、`2_processing/`、`backend/`、`frontend/` 等 | 业务、合同、API、适配器 |

业务模块（`4_business/`、`2_processing/api/`）**不得**直接 `import financepy` / `import riskfolio` / `import QuantLib`。第三方调用只允许出现在：

```text
3_riskengine/adapters/financepy/
3_riskengine/adapters/riskfolio/
3_riskengine/adapters/ore/
```

二次开发优先：import、composition、subclass、adapter、plugin、configuration、wrapper。默认不修改第三方源码。

## 补丁日志

当前 **没有** 对 FinancePy、Riskfolio-Lib、ORE 源码的修改。

| Project | Version | File | Modification | Reason | Impact | Patch |
|---|---|---|---|---|---|---|
| — | — | — | none | — | — | — |

若未来必须改第三方源码，在本表追加一行，并附补丁文件路径。
