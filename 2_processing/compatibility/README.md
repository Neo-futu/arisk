<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# 2_processing/compatibility

## 定位

Processing 层内的兼容 Facade：`api/routers` 与 `tools/` 继续对外服务；本目录逐步提供指向 `3_riskengine` / `4_business` 的委托入口。

## Wave 2

- 保留 `2_processing/tools/` 全部现有代码
- 本目录为空 package，后续按路由域添加 shim 模块
- 不得破坏 `/processing/*` 与 Backend `/api/v1/fsi/*` 代理
