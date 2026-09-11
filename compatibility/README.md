<!-- 更新时间：2026-09-09（北京时间）｜生成模型：GPT-5.4 -->

# compatibility — 兼容 Facade 层

## 迁移链

```text
Old（2_processing/tools、旧 routers）
        ↓
Compatibility（本目录说明 + 2_processing.compatibility 可导入 Facade）
        ↓
New（3_riskengine、4_business）
```

## 职责

- 保持 **API 路径、import 路径、报告与调度** 不变
- 新实现就绪后，Facade 内部切换委托目标，对外签名不变

## 可导入实现

根目录名 `compatibility` 会与已安装的第三方包冲突，因此 **Python Facade 放在**：

```text
2_processing.compatibility.load(name)
2_processing.compatibility.load_target(target_name)
4_business.<domain>.compat
```

本目录保留为迁移链文档入口，不作为 `import compatibility` 包。

## 相关

- 遗留路径登记：`legacy/`
- 类型适配：`adapter/`
