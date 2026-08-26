## Summary

- 

## Architecture Checklist

适用于新增运行时能力、改变部署形态、增加数据库 / 缓存 / worker / FUTU adapter / 常驻资源、或调整容量 / 容灾策略。纯业务逻辑、测试、文案、样式等改动可勾选“不适用”。

- [ ] 不适用：本 PR 不改变架构、运行时资源、容量、容灾或成本形态
- [ ] 已说明流量模型：平均 / 峰值 QPS、日 / 月请求量、峰谷规律、增长预期
- [ ] 已说明成本影响：主要成本来源、dev / staging / prod 成本目标或预算级别
- [ ] 已优先评估按量、serverless、scale-to-zero 或办公时段启停
- [ ] 常驻 / 预置容量资源已有理由、成本拐点和替代方案
- [ ] 已说明容量影响：并发、worker、队列、数据库连接、存储增长、日志量、保留周期
- [ ] 已说明容灾影响：prod RTO / RPO、多 AZ、备份恢复、依赖故障降级
- [ ] 如需新增接入能力，已先更新 `app-registry`，没有直接修改 `infra` 实质 IaC

## Validation

- [ ] `pytest tests/ -q`
- [ ] `cd iac && tofu fmt -check && tofu validate -backend=false`
