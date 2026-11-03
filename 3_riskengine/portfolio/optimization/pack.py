"""投资风险 / 组合配置与优化页业务模块。

页面对应 ``/portfolio-opt``。业务能力（非 UI / 非 CSV·PNG 按钮）：

1. **参数区** — 资产池、收益模型、无风险利率、权重上下限、区间
2. **优化闸门** — Riskfolio 方法提案 + 闸门状态（非成交指令）
3. **用户组合** — 可调权重与实时风险绩效
4. **有效前沿** — 前沿曲线、切点、资产点、画像落点
5. **预期收益模型** — Hist Mean / Real CAGR / CAPM / Black-Litterman / 区间实现
6. **个股风控绩效** — 收益·波动·夏普·回撤·VaR·CVaR
7. **组合画像对比** — conservative / balanced / aggressive / hrp
8. **图表数据** — 相关性矩阵 + 资产配置对比
9. **效率诊断** — alpha_loss / excess_vol

模型相对独立：本包不读库、不 import ``2_processing``；价格/收益面板经
``meta.prices`` / ``meta.returns`` 注入。闸门优化走 ``RiskEngine.riskfolio``。
"""
from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from ...core.lineage import RISKENGINE_NAME, RISKENGINE_VERSION
from . import analytics as A

BUSINESS_MODULES = (
    "parameters",
    "governed_gate",
    "user_portfolio",
    "efficient_frontier",
    "return_models",
    "asset_metrics",
    "profile_comparison",
    "charts",
    "validation",
)

NOT_TRADE_INSTRUCTION = "RiskEngine 优化结果是提案，不是交易指令。"
GATE_STEPS = (
    "optimization",
    "riskengine",
    "valuation",
    "investment_risk",
    "risk_testing",
    "limits",
)


def _frame(raw: Any) -> pd.DataFrame | None:
    if raw is None:
        return None
    if isinstance(raw, pd.DataFrame):
        return raw
    if isinstance(raw, Mapping):
        return pd.DataFrame(raw)
    return pd.DataFrame(raw)


def module_parameters(info: Mapping[str, Any], universe: list[str]) -> dict[str, Any]:
    return {
        "module": "parameters",
        "universe": universe,
        "return_model": info.get("return_model", "historical_mean"),
        "risk_free_rate": float(info.get("risk_free_rate", 0.04)),
        "weight_bounds": list(info.get("weight_bounds") or (0.0, 1.0)),
        "data_source": info.get("data_source", "meta"),
        "start_date": info.get("start_date"),
        "end_date": info.get("end_date"),
        "target_return": info.get("target_return"),
    }


def module_governed_gate(
    bound: Any,
    returns: pd.DataFrame,
    *,
    method: str,
    constraints: Mapping[str, Any] | None,
    views: Mapping[str, float] | None,
    current_weights: Mapping[str, float] | None,
) -> dict[str, Any]:
    optimization = bound.engine.riskfolio.optimize(
        returns,
        method,
        constraints=constraints,
        current_weights=current_weights,
        views=views,
    )
    # 引擎侧闸门：有权重提案即 optimization/riskengine PASS；其余由业务管道补全
    gate_status = {step: step in {"optimization", "riskengine"} for step in GATE_STEPS}
    return {
        "module": "governed_gate",
        "method": optimization.get("method", method),
        "weights": optimization.get("weights") or {},
        "risk_contribution": optimization.get("risk_contribution") or {},
        "engine": optimization.get("engine"),
        "status": "PROPOSAL",
        "is_trade_instruction": False,
        "gate_status": gate_status,
        "gate": list(GATE_STEPS),
        "note": NOT_TRADE_INSTRUCTION,
    }


def module_user_portfolio(
    weights: Mapping[str, float],
    metrics: Mapping[str, float],
) -> dict[str, Any]:
    norm = A._normalize(weights)
    return {
        "module": "user_portfolio",
        "weights": norm,
        "weight_sum_raw": float(sum(weights.values())),
        "metrics": dict(metrics),
        "note": "权重自动归一化；拖动可实时看影响",
    }


def module_efficient_frontier(
    frontier: list[dict[str, float]],
    tangency: dict[str, float] | None,
    asset_points: list[dict[str, Any]],
    profiles: Mapping[str, Any],
    risk_free_rate: float,
) -> dict[str, Any]:
    profile_points = {
        name: {
            "volatility": pack["metrics"]["volatility"],
            "expected_return": pack["metrics"]["expected_return"],
        }
        for name, pack in profiles.items()
    }
    return {
        "module": "efficient_frontier",
        "frontier": frontier,
        "tangency": tangency,
        "asset_points": asset_points,
        "profile_points": profile_points,
        "risk_free_rate": risk_free_rate,
        "note": "在左侧调整权重，此有效前沿与你的组合点位实时联动。",
    }


def module_return_models(rows: list[dict[str, Any]], return_model: str) -> dict[str, Any]:
    return {
        "module": "return_models",
        "return_model": return_model,
        "rows": rows,
        "models": ("historical_mean", "real_cagr", "capm", "black_litterman"),
    }


def module_asset_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"module": "asset_metrics", "rows": rows, "count": len(rows)}


def module_profile_comparison(profiles: Mapping[str, Any]) -> dict[str, Any]:
    names = [name for name in A.PROFILE_NAMES if name in profiles]
    for extra in profiles:
        if extra not in names:
            names.append(extra)
    return {
        "module": "profile_comparison",
        "profile_names": names,
        "profiles": {name: profiles[name] for name in names},
        "metric_keys": (
            "expected_return",
            "volatility",
            "sharpe",
            "max_drawdown",
            "var_95",
            "cvar_95",
        ),
    }


def module_charts(correlation: Mapping[str, Any], profiles: Mapping[str, Any]) -> dict[str, Any]:
    assets = sorted(
        {
            asset
            for pack in profiles.values()
            for asset, weight in (pack.get("weights") or {}).items()
            if float(weight) > 1e-4
        }
    )
    allocation = [
        {
            "asset": asset,
            **{name: float((pack.get("weights") or {}).get(asset, 0.0)) for name, pack in profiles.items()},
        }
        for asset in assets
    ]
    return {
        "module": "charts",
        "correlation": dict(correlation),
        "allocation": allocation,
        "heatmap_note": (
            "资产池内各证券收益率的两两相关性。绿色=低/负相关（分散化更好），"
            "红色=高相关（同涨同跌）。优化器偏好低相关组合以降低整体波动。"
        ),
    }


def module_validation(efficiency: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "module": "validation",
        "efficiency": dict(efficiency or {"alpha_loss": None, "excess_vol": None}),
        "is_trade_instruction": False,
        "note": NOT_TRADE_INSTRUCTION,
    }


def fundamentals(
    bound: Any,
    *,
    meta: Mapping[str, Any] | None = None,
    run_governed: bool = True,
    governed_method: str = "hrp",
) -> dict[str, Any]:
    """``/portfolio-opt`` 九大业务模块打包。"""

    info = dict(meta or {})
    prices = _frame(info.get("prices"))
    returns = _frame(info.get("returns"))
    prices, returns = A.ensure_panel(prices=prices, returns=returns)
    universe = [str(c) for c in returns.columns]
    risk_free_rate = float(info.get("risk_free_rate", 0.04))
    bounds_raw = info.get("weight_bounds") or (0.0, 0.35)
    weight_bounds = (float(bounds_raw[0]), float(bounds_raw[1]))
    return_model = str(info.get("return_model") or "historical_mean")
    target_return = info.get("target_return")
    target_return_f = None if target_return is None else float(target_return)
    views = dict(info.get("bl_views") or info.get("views") or {})
    market_caps = dict(info.get("market_caps") or {})
    custom_weights = dict(info.get("custom_weights") or {})
    if not custom_weights:
        custom_weights = {a: 1.0 / len(universe) for a in universe}

    return_rows = A.compute_return_models(
        prices,
        returns,
        risk_free_rate=risk_free_rate,
        market_caps=market_caps,
        views=views,
    )
    mu = A.select_mu(return_rows, return_model)
    cov = A.sample_cov(returns)
    asset_rows = A.asset_metrics(returns, risk_free_rate)
    profiles = A.build_profiles(
        mu,
        cov,
        returns,
        risk_free_rate=risk_free_rate,
        weight_bounds=weight_bounds,
        target_return=target_return_f,
    )
    if custom_weights:
        profiles["custom"] = {
            "weights": A._normalize(custom_weights),
            "metrics": A.portfolio_metrics(
                custom_weights, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate
            ),
        }
    bench = dict(info.get("benchmark_weights") or {})
    if bench:
        profiles["benchmark"] = {
            "weights": A._normalize(bench),
            "metrics": A.portfolio_metrics(
                bench, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate
            ),
        }

    frontier = A.efficient_frontier(mu, cov, weight_bounds=weight_bounds, points=int(info.get("frontier_points") or 40))
    tangency = A.tangency_point(mu, cov, risk_free_rate=risk_free_rate, weight_bounds=weight_bounds)
    asset_points = [
        {"asset": row["asset"], "volatility": row["volatility"], "expected_return": row["expected_return"]}
        for row in asset_rows
    ]
    correlation = A.correlation_payload(returns)
    efficiency = A.check_efficiency(
        custom_weights,
        mu=mu,
        cov=cov,
        returns=returns,
        risk_free_rate=risk_free_rate,
        weight_bounds=weight_bounds,
    )
    user_metrics = profiles.get("custom", {}).get("metrics") or A.portfolio_metrics(
        custom_weights, mu=mu, cov=cov, returns=returns, risk_free_rate=risk_free_rate
    )

    parameters = module_parameters(info, universe)
    governed = (
        module_governed_gate(
            bound,
            returns,
            method=str(info.get("governed_method") or governed_method),
            constraints={"min_weight": weight_bounds[0], "max_weight": weight_bounds[1], "max_name_weight": weight_bounds[1]},
            views=views,
            current_weights=custom_weights,
        )
        if run_governed
        else {
            "module": "governed_gate",
            "method": governed_method,
            "weights": {},
            "risk_contribution": {},
            "status": "IDLE",
            "is_trade_instruction": False,
            "gate_status": {step: False for step in GATE_STEPS},
            "gate": list(GATE_STEPS),
            "note": NOT_TRADE_INSTRUCTION,
        }
    )
    user = module_user_portfolio(custom_weights, user_metrics)
    frontier_mod = module_efficient_frontier(frontier, tangency, asset_points, profiles, risk_free_rate)
    returns_mod = module_return_models(return_rows, return_model)
    assets_mod = module_asset_metrics(asset_rows)
    profiles_mod = module_profile_comparison(profiles)
    charts = module_charts(correlation, profiles)
    validation = module_validation(efficiency)

    adapters = bound.engine.adapters_status()
    return {
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
        "page": "/portfolio-opt",
        "tab": "portfolio-opt",
        "business_modules": list(BUSINESS_MODULES),
        "is_trade_instruction": False,
        "note": NOT_TRADE_INSTRUCTION,
        "modules": {
            "parameters": parameters,
            "governed_gate": governed,
            "user_portfolio": user,
            "efficient_frontier": frontier_mod,
            "return_models": returns_mod,
            "asset_metrics": assets_mod,
            "profile_comparison": profiles_mod,
            "charts": charts,
            "validation": validation,
        },
        # HTTP OptimizeResult 同形（分析面）
        "universe": universe,
        "return_model": return_model,
        "return_models": return_rows,
        "asset_metrics": asset_rows,
        "profiles": profiles,
        "efficiency": efficiency,
        "tangency": tangency,
        "risk_free_rate": risk_free_rate,
        "frontier": frontier,
        "asset_points": asset_points,
        "correlation": correlation,
        "governed": governed,
        "adapters": adapters,
    }


def verify_business_modules(pack: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    modules = pack.get("modules") or {}
    for name in BUSINESS_MODULES:
        if name not in modules:
            errors.append(f"missing {name}")
    if not pack.get("universe"):
        errors.append("universe")
    if not pack.get("return_models"):
        errors.append("return_models")
    if not pack.get("asset_metrics"):
        errors.append("asset_metrics")
    profiles = pack.get("profiles") or {}
    for name in A.PROFILE_NAMES:
        if name not in profiles:
            errors.append(f"profiles.{name}")
        else:
            w = profiles[name].get("weights") or {}
            if abs(sum(w.values()) - 1.0) > 1e-5:
                errors.append(f"profiles.{name}.weights_sum")
    if "frontier" not in pack:
        errors.append("frontier")
    corr = pack.get("correlation") or {}
    if not corr.get("assets") or not corr.get("matrix"):
        errors.append("correlation")
    gate = modules.get("governed_gate") or {}
    if gate.get("is_trade_instruction") is not False:
        errors.append("governed_gate.is_trade_instruction")
    if pack.get("is_trade_instruction") is not False:
        errors.append("is_trade_instruction")
    return {
        "passed": not errors,
        "errors": errors,
        "business_modules": list(BUSINESS_MODULES),
        "engine": RISKENGINE_NAME,
        "engine_version": RISKENGINE_VERSION,
    }
