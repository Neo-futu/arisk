"""风险情景分析业务包（页面子菜单业务模块，非 UI）。

对应 ``/risk-testing/{sensitivity|stress|scenario|...}`` 十个子分析：
敏感度 / 压力 / 情景 / 反向压力 / 尾部风险 / KRD / PnL 归因 /
历史收益回测 / VaR 回测 / XVA。

模型相对独立：计算走 ``risk.testing`` + FinancePy / Riskfolio / ORE 适配器；
不 import ``2_processing`` / ``4_business``。情景目录来自 ``scenario.catalog``。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from ...core.contracts import RiskFactorType, Scenario, Shock, ShockMode
from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from ...scenario.catalog import SCENARIOS, scenario_catalog
from .. import testing as T

BUSINESS_MODULES = tuple(T.TESTING_ANALYTICS)

TIME_SEMANTICS = {
    "SENSITIVITY": "POINT_IN_TIME",
    "STRESS": "POINT_IN_TIME",
    "SCENARIO": "POINT_IN_TIME",
    "REVERSE_STRESS": "POINT_IN_TIME",
    "TAIL_RISK": "DATE_RANGE",
    "KRD": "POINT_IN_TIME",
    "PNL_EXPLAIN": "DATE_RANGE",
    "HISTORICAL_BACKTEST": "DATE_RANGE",
    "VAR_BACKTEST": "DATE_RANGE",
    "XVA": "POINT_IN_TIME",
}

ANALYTIC_META: dict[str, dict[str, Any]] = {
    "SENSITIVITY": {
        "label": "敏感度测试",
        "path": "/risk-testing/sensitivity",
        "description": "单一风险因子 PV / Delta / Gamma 重估",
        "formula": "Δ ≈ (PV(+h)−PV(−h))/(2h)；Γ ≈ (PV(+h)+PV(−h)−2PV)/h²",
        "adapter": "FinancePy",
        "module_key": "sensitivity",
    },
    "STRESS": {
        "label": "压力测试",
        "path": "/risk-testing/stress",
        "description": "历史及假设压力情景冲击",
        "formula": "PnL = PV(shock_set) − PV(base)；按资产类别聚合",
        "adapter": "FinancePy / ORE",
        "module_key": "stress",
    },
    "SCENARIO": {
        "label": "情景测试",
        "path": "/risk-testing/scenario",
        "description": "多因子同步变化与组合损益",
        "formula": "同步冲击再估值；披露情景定义与 by_asset_class",
        "adapter": "FinancePy / ORE",
        "module_key": "scenario",
    },
    "REVERSE_STRESS": {
        "label": "反向压力测试",
        "path": "/risk-testing/reverse-stress",
        "description": "由损失临界点反推灾难冲击",
        "formula": "二分求最小 scale 使 −PnL ≥ target_loss",
        "adapter": "FinancePy",
        "module_key": "reverse_stress",
    },
    "TAIL_RISK": {
        "label": "尾部风险测试",
        "path": "/risk-testing/tail-risk",
        "description": "3σ–5σ、VaR、CVaR 与资本充足率",
        "formula": "loss(σ)=max(−(μ−σ·s)·NAV,0)；对照 capital_buffer",
        "adapter": "Riskfolio",
        "module_key": "tail_risk",
    },
    "KRD": {
        "label": "关键利率久期 KRD",
        "path": "/risk-testing/krd",
        "description": "期限节点 PV01 与关键利率久期",
        "formula": "KRD_k = −ΔPV_k / (PV × 0.0001)；节点隔离 +1bp",
        "adapter": "FinancePy",
        "module_key": "krd",
    },
    "PNL_EXPLAIN": {
        "label": "PnL 归因",
        "path": "/risk-testing/pnl-explain",
        "description": "Carry、利率、外汇、持仓与残差解释",
        "formula": "ΔPV = Carry + Rates + FX + Position + Residual",
        "adapter": "RiskEngine attribution",
        "module_key": "pnl_explain",
    },
    "HISTORICAL_BACKTEST": {
        "label": "历史收益回测",
        "path": "/risk-testing/historical-backtest",
        "description": "以当前持仓或调整后权重回放区间真实市场行情",
        "formula": "买入持有：V_t = V_0 · Π(1+r_t)；披露 MDD / 年化波动",
        "adapter": "NumPy / market series",
        "module_key": "historical_backtest",
    },
    "VAR_BACKTEST": {
        "label": "VaR 回测",
        "path": "/risk-testing/var-backtest",
        "description": "滚动历史 VaR、例外与 Kupiec 检验",
        "formula": "Kupiec LR；例外率 vs α；交通灯 GREEN/YELLOW/RED",
        "adapter": "Riskfolio",
        "module_key": "var_backtest",
    },
    "XVA": {
        "label": "估值调整 XVA",
        "path": "/risk-testing/xva",
        "description": "CVA、DVA、FVA、MVA 暴露积分",
        "formula": "CVA≈(1−R)·Σ DF·EPE·PD；DVA/FVA/MVA 同类积分",
        "adapter": "ORE / QuantLib",
        "module_key": "xva",
    },
}

LOGIC_STEPS = (
    "load_portfolio_snapshot → RiskEngine.bind（FinancePy / ORE 估值曲线）",
    "按子分析选择：敏感度/压力/情景/反向压力（产品再估值）或尾部/VaR（Riskfolio NAV）",
    "KRD：期限节点隔离利率冲击；PnL 归因：两期快照分解；历史回测：权重×行情路径",
    "XVA：ORE 暴露曲线积分 CVA/DVA/FVA/MVA",
    "统一 stamp：engine / adapters / data_quality / assumptions → 前端 KPI + 结果表",
)

ENGINE_MODULE_PATHS = {
    key: f"3_riskengine.risk.scenario_testing.{meta['module_key']}"
    for key, meta in ANALYTIC_META.items()
}


def default_shocks() -> tuple[Shock, ...]:
    return (
        Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="利率 +1bp"),
        Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE, label="外汇 +1%"),
        Shock(RiskFactorType.VOLATILITY, 0.10, ShockMode.RELATIVE, label="波动率 +10%"),
        Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="权益 +1%"),
        Shock(RiskFactorType.CREDIT_SPREAD, 0.0001, ShockMode.ABSOLUTE, label="信用利差 +1bp"),
    )


def as_shock(item: Any) -> Shock:
    if isinstance(item, Shock):
        return item
    if isinstance(item, Mapping):
        ft = item.get("factor_type")
        mode = item.get("mode")
        return Shock(
            factor_type=RiskFactorType(str(getattr(ft, "value", ft))),
            value=float(item.get("value") or 0.0),
            mode=ShockMode(str(getattr(mode, "value", mode) or "ABSOLUTE")),
            tenor=item.get("tenor"),
            currency=item.get("currency"),
            label=str(item.get("label") or ""),
        )
    ft = getattr(item, "factor_type")
    mode = getattr(item, "mode")
    return Shock(
        factor_type=RiskFactorType(str(getattr(ft, "value", ft))),
        value=float(getattr(item, "value")),
        mode=ShockMode(str(getattr(mode, "value", mode))),
        tenor=getattr(item, "tenor", None),
        currency=getattr(item, "currency", None),
        label=str(getattr(item, "label", "") or ""),
    )


def resolve_scenario(scenario: Any = None, *, scenario_id: str | None = None) -> Scenario:
    if isinstance(scenario, Scenario):
        return scenario
    if isinstance(scenario, Mapping):
        shocks = tuple(as_shock(s) for s in (scenario.get("shocks") or ()))
        return Scenario(
            scenario_id=str(scenario.get("scenario_id") or "custom"),
            name=str(scenario.get("name") or "自定义情景"),
            category=str(scenario.get("category") or "custom"),
            shocks=shocks,
            description=str(scenario.get("description") or ""),
        )
    if scenario is not None and hasattr(scenario, "shocks"):
        return Scenario(
            scenario_id=str(getattr(scenario, "scenario_id", "custom")),
            name=str(getattr(scenario, "name", "情景")),
            category=str(getattr(scenario, "category", "custom")),
            shocks=tuple(as_shock(s) for s in getattr(scenario, "shocks")),
            description=str(getattr(scenario, "description", "") or ""),
        )
    key = scenario_id or "gfc_2008"
    if key not in SCENARIOS:
        raise ValueError(f"Unknown scenario_id: {key}")
    return SCENARIOS[key]


def catalog() -> list[dict[str, Any]]:
    rows = []
    for analytic, meta in ANALYTIC_META.items():
        rows.append(
            {
                "analytic": analytic,
                "label": meta["label"],
                "path": meta["path"],
                "description": meta["description"],
                "formula": meta["formula"],
                "adapter": meta["adapter"],
                "time_semantics": TIME_SEMANTICS[analytic],
                "engine_module": ENGINE_MODULE_PATHS[analytic],
            }
        )
    return rows


def _result_rows(analytic: str, report: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = (
        "sensitivities",
        "buckets",
        "tail_scenarios",
        "positions",
        "backtest_points",
        "points",
        "trade_values",
        "exposure_profile",
    )
    for key in keys:
        rows = report.get(key)
        if isinstance(rows, list) and rows:
            return [dict(row) if isinstance(row, Mapping) else {"value": row} for row in rows]
    by_class = report.get("by_asset_class")
    if isinstance(by_class, Mapping) and by_class:
        return [{"asset_class": k, **(v if isinstance(v, Mapping) else {"value": v})} for k, v in by_class.items()]
    return []


def _kpi_cards(analytic: str, report: Mapping[str, Any]) -> list[dict[str, Any]]:
    cards = [
        {
            "label": "组合净资产",
            "value": report.get("net_asset"),
            "detail": report.get("reporting_currency"),
        },
        {
            "label": "估值/冲击损益",
            "value": report.get("pnl"),
            "detail": None if report.get("pnl_pct_nav") is None else f"{report.get('pnl_pct_nav')}% NAV",
        },
        {
            "label": "数据持仓数",
            "value": (report.get("data_quality") or {}).get("position_count"),
            "detail": (report.get("data_quality") or {}).get("effective_date") or report.get("as_of_date"),
        },
        {
            "label": "运行状态",
            "value": report.get("status") or "OK",
            "detail": f"{report.get('library') or report.get('engine')} · {analytic}",
        },
    ]
    if analytic == "XVA":
        for key in ("cva", "dva", "fva", "mva"):
            cards.append({"label": key.upper(), "value": report.get(key), "detail": None})
    if analytic == "HISTORICAL_BACKTEST":
        cards.extend(
            [
                {"label": "区间总收益", "value": report.get("total_return_pct"), "detail": "%"},
                {"label": "年化收益", "value": report.get("annualized_return_pct"), "detail": "%"},
                {"label": "年化波动率", "value": report.get("annualized_volatility_pct"), "detail": "%"},
                {"label": "最大回撤", "value": report.get("max_drawdown_pct"), "detail": "%"},
            ]
        )
    if analytic == "VAR_BACKTEST":
        cards.extend(
            [
                {"label": "例外次数", "value": report.get("exceptions"), "detail": None},
                {"label": "例外率", "value": report.get("exception_rate_pct"), "detail": "%"},
                {"label": "Kupiec LR", "value": report.get("kupiec_lr"), "detail": None},
                {"label": "交通灯", "value": report.get("traffic_light"), "detail": None},
            ]
        )
    if analytic == "REVERSE_STRESS":
        cards.extend(
            [
                {"label": "是否触及损失", "value": report.get("breach_reached"), "detail": None},
                {"label": "临界倍数", "value": report.get("critical_scale"), "detail": None},
                {"label": "目标损失", "value": report.get("target_loss_amount"), "detail": None},
            ]
        )
    if analytic == "KRD":
        cards.append({"label": "组合 PV01", "value": report.get("portfolio_pv01"), "detail": None})
    return cards


def present_modules(analytic: str, report: Mapping[str, Any]) -> dict[str, Any]:
    key = str(analytic).upper()
    meta = ANALYTIC_META.get(key) or {"label": key, "formula": "", "description": "", "adapter": "", "path": ""}
    return {
        "parameters": {
            "module": "parameters",
            "analytic": key,
            "time_semantics": TIME_SEMANTICS.get(key),
            "label": meta["label"],
            "description": meta.get("description"),
        },
        "kpi_cards": {"module": "kpi_cards", "rows": _kpi_cards(key, report)},
        "result_table": {
            "module": "result_table",
            "title": "结构化风险结果",
            "rows": _result_rows(key, report),
            "exportable": True,
        },
        "data_quality": {
            "module": "data_quality",
            "payload": dict(report.get("data_quality") or {}),
            "assumptions": list(report.get("assumptions") or []),
        },
        "methodology": {
            "module": "methodology",
            "formula": meta.get("formula"),
            "adapter": meta.get("adapter"),
            "logic": {"title": "RiskEngine 风险情景分析实现逻辑", "steps": list(LOGIC_STEPS)},
            "engine_module": ENGINE_MODULE_PATHS.get(key),
        },
    }


def run_analytic(
    bound: Any,
    analytic: str = "SENSITIVITY",
    *,
    shocks: Iterable[Any] | None = None,
    scenario: Any = None,
    scenario_id: str | None = None,
    target_loss_pct_nav: float = 10.0,
    max_scale: float = 20.0,
    sigma_levels: Sequence[float] | None = None,
    capital_buffer: float | None = None,
    bump_bps: float = 1.0,
    previous: Any | None = None,
    market: Any | None = None,
    weight_mode: str = "CURRENT",
    custom_weights: Mapping[str, float] | None = None,
    confidence: float = 0.99,
    window: int = 60,
    counterparty_hazard: float = 0.02,
    own_hazard: float = 0.01,
    recovery_rate: float = 0.40,
    funding_spread: float = 0.01,
    initial_margin_pct: float = 0.05,
    mva_funding_spread: float = 0.008,
) -> dict[str, Any]:
    """运行单一风险情景分析业务模块，附加页面 modules 视图。"""

    key = str(analytic).upper()
    shock_tuple = tuple(as_shock(s) for s in (shocks or ())) or default_shocks()
    scen = None
    if key in {"STRESS", "SCENARIO", "REVERSE_STRESS"}:
        scen = resolve_scenario(scenario, scenario_id=scenario_id)

    if key == "SENSITIVITY":
        report = T.sensitivity(bound, shock_tuple)
    elif key == "STRESS":
        report = T.stress(bound, scen)
    elif key == "SCENARIO":
        report = T.scenario(bound, scen)
    elif key == "REVERSE_STRESS":
        report = T.reverse_stress(bound, scen, target_loss_pct_nav, max_scale)
    elif key == "TAIL_RISK":
        capital = capital_buffer
        if capital is None:
            capital = float(getattr(bound.snapshot, "net_asset", 0.0) or 0.0) * 0.08
        report = T.tail_risk(bound, sigma_levels or (3.0, 4.0, 5.0), float(capital))
    elif key == "KRD":
        report = T.krd(bound, bump_bps)
    elif key == "PNL_EXPLAIN":
        if previous is None:
            raise ValueError("PNL_EXPLAIN requires previous snapshot")
        report = T.pnl_explain(bound, previous)
    elif key == "HISTORICAL_BACKTEST":
        report = T.historical_backtest(
            bound,
            market=market,
            weight_mode=weight_mode,
            custom_weights=custom_weights,
        )
    elif key == "VAR_BACKTEST":
        report = T.var_backtest(bound, confidence=confidence, window=window)
    elif key == "XVA":
        report = T.xva(
            bound,
            counterparty_hazard=counterparty_hazard,
            own_hazard=own_hazard,
            recovery_rate=recovery_rate,
            funding_spread=funding_spread,
            initial_margin_pct=initial_margin_pct,
            mva_funding_spread=mva_funding_spread,
        )
    else:
        raise ValueError(f"Unsupported analytic: {analytic}")

    report.setdefault("status", "OK")
    report.setdefault("library", report.get("model") or RISKENGINE_NAME)
    report.setdefault("engine", RISKENGINE_NAME)
    report.setdefault("engine_version", RISKENGINE_VERSION)
    meta = ANALYTIC_META.get(key) or {}
    report["implementation"] = {
        "business_module": ENGINE_MODULE_PATHS.get(key, f"3_riskengine.risk.testing.{key.lower()}"),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "adapter": meta.get("adapter"),
        "formula": meta.get("formula"),
        "time_semantics": TIME_SEMANTICS.get(key),
        "portfolio_data_module": "risk_testing.loader",
        "is_trade_instruction": False,
    }
    report["page"] = meta.get("path") or f"/risk-testing/{key.lower()}"
    report["tab"] = key.lower().replace("_", "-")
    report["business_modules"] = list(BUSINESS_MODULES)
    report["modules"] = present_modules(key, report)
    report["formulas"] = {k: v["formula"] for k, v in ANALYTIC_META.items()}
    report["logic"] = {"title": "RiskEngine 风险情景分析实现逻辑", "steps": list(LOGIC_STEPS)}
    report["scenario_catalog"] = scenario_catalog() if key in {"STRESS", "SCENARIO", "REVERSE_STRESS"} else None
    return report


def fundamentals(bound: Any, analytic: str = "SENSITIVITY", **kwargs: Any) -> dict[str, Any]:
    """页面打包入口（同 ``run_analytic``）。"""

    return run_analytic(bound, analytic, **kwargs)


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    analytic = str(pack.get("analytic") or "").upper()
    if analytic not in BUSINESS_MODULES:
        errors.append("analytic")
    modules = pack.get("modules") or {}
    for key in ("parameters", "kpi_cards", "result_table", "data_quality", "methodology"):
        if key not in modules:
            errors.append(f"modules.{key}")
    if "implementation" not in pack:
        errors.append("implementation")
    if pack.get("engine") not in {RISKENGINE_NAME, "ARISK RiskEngine", None} and not pack.get("engine"):
        errors.append("engine")
    return {"passed": not errors, "errors": errors}
