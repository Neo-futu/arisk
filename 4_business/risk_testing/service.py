"""Risk Testing use-case layer.

Orchestrates existing ARISK portfolio/market loaders and RiskEngine analytics.
Does not create a second Portfolio / Position / Market Data store.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from importlib import import_module

_rt = import_module("2_processing.tools.risk_testing")
_analytics = import_module("2_processing.tools.risk_testing.analytics")
_financepy = import_module("2_processing.tools.risk_testing.financepy_adapter")
_market = import_module("2_processing.tools.risk_testing.market_data")
_models = import_module("2_processing.tools.risk_testing.models")
_engine_mod = import_module("3_riskengine")
_limits = import_module("3_riskengine.limits")

ProfessionalRiskEngine = _rt.ProfessionalRiskEngine
SCENARIOS = _rt.SCENARIOS
load_portfolio_snapshot = _rt.load_portfolio_snapshot
scenario_catalog = _rt.scenario_catalog
RiskEngine = _engine_mod.RiskEngine
FINANCEPY_CORE_CALLS = _financepy.FINANCEPY_CORE_CALLS
Shock = _models.Shock
Scenario = _models.Scenario
RiskFactorType = _models.RiskFactorType
ShockMode = _models.ShockMode

historical_backtest = _analytics.historical_backtest
krd = _analytics.krd
pnl_explain = _analytics.pnl_explain
reverse_stress = _analytics.reverse_stress
scenario_analytic = _analytics.scenario
sensitivity = _analytics.sensitivity
stress = _analytics.stress
tail_risk = _analytics.tail_risk
var_backtest = _analytics.var_backtest
xva = _analytics.xva
load_historical_market_data = _market.load_historical_market_data

logger = logging.getLogger(__name__)

PYTHON_MODULES = {
    "SENSITIVITY": "risk_testing.analytics.sensitivity.run",
    "STRESS": "risk_testing.analytics.stress.run",
    "SCENARIO": "risk_testing.analytics.scenario.run",
    "REVERSE_STRESS": "risk_testing.analytics.reverse_stress.run",
    "TAIL_RISK": "risk_testing.analytics.tail_risk.run",
    "KRD": "risk_testing.analytics.krd.run",
    "PNL_EXPLAIN": "risk_testing.analytics.pnl_explain.run",
    "HISTORICAL_BACKTEST": "risk_testing.analytics.historical_backtest.run",
    "VAR_BACKTEST": "risk_testing.analytics.var_backtest.run",
    "XVA": "risk_testing.analytics.xva.run",
}

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


def default_sensitivities() -> tuple[Any, ...]:
    return (
        Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="利率 +1bp"),
        Shock(RiskFactorType.FX, 0.01, ShockMode.RELATIVE, label="外汇 ±1%"),
        Shock(RiskFactorType.VOLATILITY, 0.10, ShockMode.RELATIVE, label="波动率 +10%"),
        Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="权益价格 ±1%"),
        Shock(RiskFactorType.CREDIT_SPREAD, 0.0001, ShockMode.ABSOLUTE, label="信用利差 +1bp"),
    )


def resolve_scenario(request: Any) -> Any:
    if request.shocks:
        return Scenario(
            scenario_id="custom",
            name=request.scenario_name,
            category="custom",
            shocks=tuple(item.to_domain() for item in request.shocks),
            description="User-defined multi-factor scenario",
        )
    if request.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=422, detail="Unknown scenario_id")
    return SCENARIOS[request.scenario_id]


def capabilities_payload(analytics: list[str]) -> dict[str, Any]:
    status = RiskEngine().adapters_status()
    financepy = status["financepy"]
    return {
        "module": "risk_testing",
        "engine": "FinancePy Professional Risk Engine",
        "riskengine": status["engine"],
        "riskengine_version": status["engine_version"],
        "financepy_available": bool(financepy["available"]),
        "financepy_version": financepy["version"],
        "adapters": status,
        "analytics": analytics,
        "python_modules": PYTHON_MODULES,
        "data_modules": {
            "portfolio": "risk_testing.portfolio_data",
            "market": "risk_testing.market_data",
            "orchestrator": "risk_testing.loader.load_portfolio_snapshot",
        },
        "financepy_core_calls": list(FINANCEPY_CORE_CALLS),
        "time_semantics": TIME_SEMANTICS,
        "interfaces": ["REST JSON", "REST XML", "Python", "Jupyter", "Excel/LibreOffice CSV"],
        "scenarios": scenario_catalog(),
        "limit_engine": "3_riskengine.limits",
        "limit_ids": list(_limits.LIMIT_IDS),
    }


def holdings_payload(fund_id: str, requested: date, snapshot: Any) -> dict[str, Any]:
    total = sum(max(position.market_value_base, 0.0) for position in snapshot.positions)
    return {
        "fund_id": fund_id,
        "requested_date": requested.isoformat(),
        "effective_date": snapshot.as_of_date.isoformat(),
        "reporting_currency": snapshot.reporting_currency,
        "holdings": [
            {
                "security_code": position.security_code,
                "security_name": position.security_name,
                "asset_class": position.asset_class,
                "market_value_base": position.market_value_base,
                "current_weight_pct": (
                    max(position.market_value_base, 0.0) / total * 100.0 if total else 0.0
                ),
            }
            for position in sorted(snapshot.positions, key=lambda item: item.market_value_base, reverse=True)
        ],
    }


def period_start(request: Any, default_days: int = 365) -> date:
    start_date = request.start_date or request.as_of_date - timedelta(days=default_days)
    if start_date >= request.as_of_date:
        raise HTTPException(status_code=422, detail="start_date must be earlier than as_of_date")
    return start_date


def _stamp_riskengine(result: dict[str, Any], snapshot: Any, analytic: str) -> dict[str, Any]:
    status = RiskEngine().adapters_status()
    result.setdefault("riskengine", status["engine"])
    result.setdefault("engine_version", status["engine_version"])
    result.setdefault("model_version", status["engine_version"])
    result.setdefault("valuation_date", snapshot.as_of_date.isoformat())
    result.setdefault("market_data_date", snapshot.as_of_date.isoformat())
    result.setdefault("curve", "FinancePy FlatDiscountCurve (DiscountCurveFlat compatible)")
    result.setdefault("adapters", status)
    if analytic == "VAR_BACKTEST":
        returns = [item[1] for item in snapshot.nav_returns]
        result.setdefault(
            "cross_engine",
            {"riskfolio": RiskEngine().riskfolio.historical_var_cvar(returns, result.get("confidence", 0.99))},
        )
    if analytic == "XVA":
        result.setdefault("ore_adapter", status["ore"])
    result.setdefault("limits", _limits.evaluate(snapshot))
    result.setdefault("limit_engine", "3_riskengine.limits")
    return result


def log_runtime_trace(fund_id: str, request: Any, result: dict[str, Any]) -> None:
    implementation = result.get("implementation")
    scenario = result.get("scenario") if isinstance(result.get("scenario"), dict) else None
    shocks = scenario.get("shocks") if isinstance(scenario, dict) else None
    logger.info(
        "risk-testing execution fund=%s analytic=%s scenario=%s implementation=%s shocks=%s",
        fund_id,
        request.analytic.value,
        request.scenario_id,
        json.dumps(implementation, ensure_ascii=True, default=str),
        json.dumps(shocks, ensure_ascii=True, default=str),
    )


async def execute_risk_test(fund_id: str, request: Any, db: AsyncSession) -> dict[str, Any]:
    """Run one Risk Testing analytic. API contract is unchanged."""

    try:
        requested_history_days = request.lookback_days
        if request.start_date is not None:
            requested_history_days = max(
                requested_history_days,
                (request.as_of_date - request.start_date).days + 30,
            )
        snapshot = await load_portfolio_snapshot(fund_id, request.as_of_date, db, requested_history_days)
        engine = ProfessionalRiskEngine(snapshot)
        analytic = request.analytic.value if hasattr(request.analytic, "value") else str(request.analytic)
        result: dict[str, Any]
        if analytic == "SENSITIVITY":
            shocks = tuple(item.to_domain() for item in request.shocks) or default_sensitivities()
            result = sensitivity.run(engine, shocks)
        elif analytic == "STRESS":
            result = stress.run(engine, resolve_scenario(request))
        elif analytic == "SCENARIO":
            result = scenario_analytic.run(engine, resolve_scenario(request))
        elif analytic == "REVERSE_STRESS":
            result = reverse_stress.run(
                engine,
                resolve_scenario(request),
                request.target_loss_pct_nav,
                request.max_reverse_scale,
            )
        elif analytic == "TAIL_RISK":
            start_date = period_start(request)
            snapshot.nav_returns = [item for item in snapshot.nav_returns if item[0] >= start_date]
            engine = ProfessionalRiskEngine(snapshot)
            capital = snapshot.net_asset * request.capital_buffer_pct_nav / 100.0
            result = tail_risk.run(engine, request.sigma_levels, capital)
        elif analytic == "KRD":
            result = krd.run(engine, request.rate_bump_bps)
        elif analytic == "PNL_EXPLAIN":
            start_date = period_start(request, 30)
            previous = await load_portfolio_snapshot(fund_id, start_date, db, request.lookback_days)
            result = pnl_explain.run(engine, previous)
        elif analytic == "HISTORICAL_BACKTEST":
            start_date = period_start(request)
            market = await load_historical_market_data(
                fund_id,
                snapshot.positions,
                start_date,
                snapshot.as_of_date,
                snapshot.reporting_currency,
                db,
            )
            result = historical_backtest.run(
                snapshot,
                market,
                request.weight_mode.value,
                request.custom_weights,
            )
        elif analytic == "VAR_BACKTEST":
            start_date = period_start(request)
            snapshot.nav_returns = [item for item in snapshot.nav_returns if item[0] >= start_date]
            engine = ProfessionalRiskEngine(snapshot)
            result = var_backtest.run(engine, request.confidence, request.backtest_window)
        elif analytic == "XVA":
            result = xva.run(
                engine,
                request.counterparty_hazard,
                request.own_hazard,
                request.recovery_rate,
                request.funding_spread,
                request.initial_margin_pct,
                request.mva_funding_spread,
            )
        else:
            raise HTTPException(status_code=422, detail="Unsupported analytic")
        result = _stamp_riskengine(result, snapshot, analytic)
        log_runtime_trace(fund_id, request, result)
        return result
    except HTTPException:
        raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="FinancePy is not installed in the processing runtime") from exc


def run(snapshot: Any, analytic: str = "SENSITIVITY", **kwargs: Any) -> dict[str, Any]:
    """Run one Risk Testing analytic on RiskEngine. HTTP execute_risk_test stays on PRE."""

    bound = RiskEngine().bind(snapshot)
    key = str(analytic).upper()
    if key == "SENSITIVITY":
        report = bound.risk().sensitivity(kwargs.get("shocks") or default_sensitivities())
    elif key == "STRESS":
        report = bound.risk().stress(kwargs.get("scenario") or SCENARIOS["gfc_2008"])
    elif key == "SCENARIO":
        report = bound.risk().scenario(kwargs.get("scenario") or SCENARIOS["fed_hike_75"])
    elif key == "REVERSE_STRESS":
        report = bound.risk().reverse_stress(
            kwargs.get("scenario") or SCENARIOS["gfc_2008"],
            kwargs.get("target_loss_pct_nav", 5.0),
            kwargs.get("max_scale", 20.0),
        )
    elif key == "TAIL_RISK":
        capital = kwargs.get("capital_buffer")
        if capital is None:
            capital = float(snapshot.net_asset or 0.0) * 0.08
        report = bound.risk().tail_risk(kwargs.get("sigma_levels") or (3.0, 4.0, 5.0), capital)
    elif key == "KRD":
        report = bound.risk().krd(kwargs.get("bump_bps", 1.0))
    elif key == "PNL_EXPLAIN":
        previous = kwargs.get("previous")
        if previous is None:
            raise ValueError("PNL_EXPLAIN requires previous snapshot")
        report = bound.pnl().explain(previous)
    elif key == "HISTORICAL_BACKTEST":
        report = bound.risk().historical_backtest(market=kwargs.get("market"))
    elif key == "VAR_BACKTEST":
        report = bound.risk().var_backtest(kwargs.get("confidence", 0.99), kwargs.get("window", 60))
    elif key == "XVA":
        report = bound.counterparty().xva()
    else:
        report = bound.risk().calculate(key, **kwargs)
    return _stamp_riskengine(report, snapshot, key)
