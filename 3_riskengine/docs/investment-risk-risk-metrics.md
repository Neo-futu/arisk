<!-- 更新时间：2026-11-03（北京时间）｜生成模型：Composer -->

# 投资风险 · 风险指标 Tab 业务模块 × RiskEngine

页面入口：`http://localhost:5173/investment-risk/indicators#risk-exposure`（「风险指标」页签）  
引擎入口：`RiskEngine().bind(snapshot).portfolio().risk_indicators()`  
实现：`3_riskengine/portfolio/risk_indicators.py`  
业务域：`4_business.investment_risk.exposure`

本文说明的是**资管风控业务指标**，不是工具栏 / Tab 壳 / CSV。  
同页「基本信息」见 [`investment-risk-indicators.md`](investment-risk-indicators.md)。

---

## 1. 业务模块

| 模块 | 引擎键 | 页面 |
|---|---|---|
| 核心风险轮廓 | `modules.core_profile` | 顶部五卡 |
| 滚动波动率 | `modules.rolling_volatility` | 滚动波动图 / 组合回撤 |
| VaR 三方法 | `modules.var_compare` | 日度 VaR 对比 |
| 六大风控类型看板 | `modules.metric_board` | 市场 / 信用 / 流动性 / 集中度 / 合规 / 压力 |

```python
pack = RiskEngine().bind(snapshot).portfolio().risk_indicators(
    meta={"extensions": {"avg_pe": 18.6, "implied_pd": 0.35, "neg_news": 1}},
)
assert pack["business_modules"] == [
    "core_profile", "rolling_volatility", "var_compare", "metric_board",
]
```

市数扩展字段（PE/PB/风格/隐含 PD/舆情/投资者/关联方等）经 `meta.extensions` 注入，与 processing SQL 对账。

---

## 2. 市场风险 `market`

| 指标 id | 名称 | 口径 / 来源 |
|---|---|---|
| `interval_return` | 区间收益率 | \(\Pi(1+r)-1\) · 核心风险指标 |
| `day_return` | 涨跌幅（日） | 末日 NAV 收益 ×100 |
| `annualized_vol` | 年化波动率 | \(\mathrm{stdev}(r)\times\sqrt{252}\) |
| `max_drawdown` | 最大回撤 | 财富曲线峰谷 |
| `equity_beta` | 组合 Beta | \(\mathrm{Cov}/\mathrm{Var}(R_b)\) |
| `sharpe` | 夏普比率 | \(\bar r/\sigma\times\sqrt{252}\) |
| `info_ratio` | 信息比率 | 主动收益 / TE（需基准，如 HSI） |
| `tracking_error` | 跟踪误差（年化） | \(\mathrm{stdev}(R_p-R_b)\times\sqrt{252}\) |
| `rolling_vol_latest` | 滚动波动率（最新） | 窗口年化波动末点 |
| `daily_var_pct` | 日度VaR | 历史模拟 `%NAV` |
| `turnover` | 股票年化换手率 | meta 成交 / 日均股票余额 |
| `duration` / `modified_duration` | 组合久期 / 修正久期 | FI 市值加权 |
| `dv01` | DV01 | 久期代理 / 1bp 再定价 |
| `convexity` | 凸性 | 债市值加权 |
| `avg_remaining` | 平均剩余期限 | 至到期年 |
| `credit_spread` | 信用利差 | `mktdata_fi_credit` 或 YTM−2% 代理 |
| `style_deviation` | 投资风格偏离（成长−价值） | `mktdata_equity_style` |
| `avg_pe` / `avg_pb` | 平均市盈率 / 市净率 | `mktdata_quotes` |
| `factor_*_exposure` | 因子敞口 EQUITY / RATE_CREDIT / FX | RiskEngine Factor Exposure |
| `factor_beta` | 因子 Beta | RiskEngine Beta |
| `factor_tracking_error` | Tracking Error | RiskEngine TE |
| `fx_exposure` | 汇率风险敞口占比 | 非本位币资产 / NAV |
| `non_cny_pct` | 境外非人民币资产占比 | 非 CNY/CNH |
| `country_conc` | 国家/地区集中度 | 最大国别权重 + 明细 |

另有独立模块：`rolling_volatility`（全序列）、`var_compare`（三方法）。

---

## 3. 信用风险 `credit`

| 指标 id | 名称 | 口径 |
|---|---|---|
| `issuer_rating_dist` / `debt_rating_dist` | 主体 / 债项评级档位数 | 分布明细进 `detail` 与 `credit_rating_detail` |
| `issuer_ig_pct` / `*_below_ig_pct` | 投资级 / 低于投资级占比 | BBB- 及以上 |
| `issuer_hhi` / `top_issuer_pct` | 发行人 HHI / 最大发行人 | 债市值 |
| `bond_top5` / `bond_top10` | 前五大 / 十大个券集中度 | |
| `controller_conc` | 同一实际控制人集中度 | 集团穿透 / meta |
| `cs01` | CS01 | 利差 1bp 代理 |
| `implied_pd` | 隐含违约率 | `mktdata_fi_credit` |
| `neg_news` | 负面舆情条数 | `mktdata_issuer_news` |

主体 / 债项评级明细表：`credit_rating_detail.issuer_rating_distribution` / `debt_rating_distribution`。

---

## 4. 流动性风险 `liquidity`

| 指标 id | 名称 | 口径 |
|---|---|---|
| `ttl_10` / `ttl_25` / `ttl_50` | 变现天数 TTL 10/25/50% | 流动性桶阶梯累计至 NAV×k% |
| `avg_ttl` / `bond_ttl` / `stock_ttl` | 平均 / 债 / 股变现天数 | 市值加权天数 |
| `over_10d` / `over_40d` | 变现超 10/40 天资产占比 | |
| `cash_pct` | 现金及高流动性资产占比 | T0+1W+1M 或短久期 |
| `cash_only` | 现金及存款占比 | CASH+DEPOSIT |
| `rate_bond_pct` | 国债/利率债占比 | |
| `restricted_pct` | 流动受限资产占比 | 停牌 / 不可卖出 |
| `lcr_15` | 高流动性覆盖率（赎回 15%） | 高流动性% / 15 |
| `net_redemption` | 净赎回占期初净值 | 申赎流水（meta） |
| `investor_conc` | 前十大投资者集中度 | meta |

---

## 5. 集中度与杠杆 `concentration`

| 指标 id | 名称 |
|---|---|
| `equity_top5` / `equity_top10` / `equity_largest` | 前五 / 十大 / 最大个股占比 |
| `equity_hhi` / `sector_hhi` | 个股 / 行业 HHI |
| `equity_float` | 最大个股占流通股（`mktdata_stock_static`） |
| `bond_conc_top10` / `issuer_top` | 前十大债 / 最大发行人（债） |
| `controller_eq` | 同一实际控制人集中度 |
| `country_qdii` | 国家/地区集中度 |
| `leverage` | 杠杆倍数（资产/净值） |
| `repo_pct` | 正回购负债占比 |

---

## 6. 投资合规与操作 `compliance`

| 指标 id | 名称 | 限额口径（示例） |
|---|---|---|
| `ams_wam` | WAM 加权平均届满期 | ≤60 天 · AMS 2.2 硬指标 |
| `ams_wal` | WAL 加权平均有效期 | ≤120 天 · AMS 2.4 |
| `ams_wla` | WLA 每周流动资产 | ≥15% · AMS 2.6 |
| `ams_wam_internal` | WAM（内部从严） | 默认 ≤50 天 · AMS 3.29 |
| `ams_wal_internal` | WAL（内部从严） | 默认 ≤100 天 · AMS 3.30 |
| `ams_wla_internal` | WLA（内部从严） | 默认 ≥20% · AMS 3.32 |
| `ams_single_issuer` | 单一主体 | ≤10% · AMS 2.3 |
| `process_exceptions` | 流程异常节点数 | 待处理审核 |
| `counterparty_limit_usage` | 交易对手限额使用率 | 回购本金/授信 |
| `regulatory_redlines` | 监管红线触发数 | |
| `related_party_pct` | 关联交易持仓占比 | `para_port_related_party` |
| `deposit_bank_usage` | 存款行额度使用率 | ≤100% 硬指标 |

`note` 字段含「合规 / 超限 · AMS 码 · 方案 · 硬/内部 · 限额」。

---

## 7. 产品压力测试 `stress`

| 指标 id | 名称 |
|---|---|
| `rate_shock_50` / `_pct` | 利率 +50BP 偏离金额 / 占比 |
| `redemption_15_lcr` / `redemption_20_lcr` | 赎回 15%/20% 高流动性覆盖率 |
| `market_crash_nav` | 股指极端下跌代理 β×(−20%) |
| `credit_default_3` | 信用违约 3%·净值损失 |
| `top5_investor_redeem` | 前五大投资者全部赎回覆盖率 |

---

## 8. 数据流

```
NAV 序列              → 收益 / 波动 / 回撤 / 滚动波动 / VaR / Sharpe / TE / IR
持仓穿透 + 再定价     → 久期 / DV01 / CS01 / 因子敞口 / 评级 / 集中度 / TTL
liquidity buckets     → WLA / 高流动性 / 变现天数
mmf.sfc_metrics       → WAM / WAL
meta.extensions       → PE/PB/风格/隐含PD/舆情/投资者/关联方/操作限额
        ↓
portfolio().risk_indicators()
        ↓
四大模块 + 六类全量指标行（与 HTTP metric-board 对账）
```

HTTP：

- `GET .../risk-indicators/{fund_id}`
- `GET .../risk-indicators-timeseries/{fund_id}`
- `GET .../risk/var-compare/{fund_id}`
- `GET .../risk-metric-board/{fund_id}`

---

## 9. 验证

```bash
python 3_riskengine/scripts/run_tests.py tests/test_investment_risk_risk_metrics.py -q
```

断言：`REQUIRED_METRIC_IDS` 六类齐全；核心 / 利率信用 / 因子 / TTL / AMS / 操作限额样例值可注入对账。

---

## 10. 边界

- 依赖专用市数表的字段（风格、PE/PB、隐含 PD、舆情、流通股本、投资者）无 `meta.extensions`；无注入时标 `unavailable`。
- VaR / 回撤 / 波动是风险估计，不是会计或监管资本。
- AMS 内部从严限额可由 `wam_internal_limit` / `wal_internal_limit` / `wla_internal_limit` 覆盖。
- 厂商仅 `adapters/`；本业务不直接 import FinancePy / ORE / Riskfolio。
