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
_financepy = import_module("2_processing.tools.risk_testing.financepy_adapter")
_market = import_module("2_processing.tools.risk_testing.market_data")
_models = import_module("2_processing.tools.risk_testing.models")
_engine_mod = import_module("3_riskengine")
_limits = import_module("3_riskengine.limits")
_scenario_testing = import_module("3_riskengine.risk.scenario_testing")

SCENARIOS = _rt.SCENARIOS
load_portfolio_snapshot = _rt.load_portfolio_snapshot
scenario_catalog = _rt.scenario_catalog
RiskEngine = _engine_mod.RiskEngine
FINANCEPY_CORE_CALLS = _financepy.FINANCEPY_CORE_CALLS
Shock = _models.Shock
Scenario = _models.Scenario
RiskFactorType = _models.RiskFactorType
ShockMode = _models.ShockMode

load_historical_market_data = _market.load_historical_market_data

logger = logging.getLogger(__name__)

PYTHON_MODULES = dict(_scenario_testing.ENGINE_MODULE_PATHS)
TIME_SEMANTICS = dict(_scenario_testing.TIME_SEMANTICS)


def default_sensitivities() -> tuple[Any, ...]:
    return _scenario_testing.default_shocks()


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
        "engine": status["engine"],
        "engine_version": status["engine_version"],
        "riskengine": status["engine"],
        "riskengine_version": status["engine_version"],
        "financepy_available": bool(financepy["available"]),
        "financepy_version": financepy["version"],
        "adapters": status,
        "analytics": analytics,
        "python_modules": PYTHON_MODULES,
        "business_modules": list(_scenario_testing.BUSINESS_MODULES),
        "catalog": _scenario_testing.catalog(),
        "data_modules": {
            "portfolio": "risk_testing.portfolio_data",
            "market": "risk_testing.market_data",
            "orchestrator": "risk_testing.loader.load_portfolio_snapshot",
            "engine_pack": "3_riskengine.risk.scenario_testing",
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
    if not result.get("status"):
        result["status"] = "OK"
    if not result.get("analytic"):
        result["analytic"] = analytic
    result.setdefault("riskengine", status["engine"])
    result.setdefault("engine", status["engine"])
    result.setdefault("engine_version", status["engine_version"])
    result.setdefault("model_version", status["engine_version"])
    result.setdefault("valuation_date", snapshot.as_of_date.isoformat())
    result.setdefault("market_data_date", snapshot.as_of_date.isoformat())
    result.setdefault("curve", "FinancePy FlatDiscountCurve (DiscountCurveFlat compatible)")
    result.setdefault("adapters", status)
    result.setdefault("library", result.get("library") or status["engine"])
    quality = dict(result.get("data_quality") or {})
    if not quality.get("effective_date"):
        quality["effective_date"] = snapshot.as_of_date.isoformat()
    if quality.get("position_count") is None:
        quality["position_count"] = len(getattr(snapshot, "positions", []) or [])
    result["data_quality"] = quality
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
    """Run one Risk Testing analytic via RiskEngine scenario_testing pack."""

    try:
        requested_history_days = request.lookback_days
        if request.start_date is not None:
            requested_history_days = max(
                requested_history_days,
                (request.as_of_date - request.start_date).days + 30,
            )
        snapshot = await load_portfolio_snapshot(fund_id, request.as_of_date, db, requested_history_days)
        analytic = request.analytic.value if hasattr(request.analytic, "value") else str(request.analytic)
        bound = RiskEngine().bind(snapshot)

        kwargs: dict[str, Any] = {}
        if analytic == "SENSITIVITY":
            shocks = tuple(item.to_domain() for item in request.shocks) or default_sensitivities()
            kwargs["shocks"] = shocks
        elif analytic in {"STRESS", "SCENARIO", "REVERSE_STRESS"}:
            kwargs["scenario"] = resolve_scenario(request)
            if analytic == "REVERSE_STRESS":
                kwargs["target_loss_pct_nav"] = request.target_loss_pct_nav
                kwargs["max_scale"] = request.max_reverse_scale
        elif analytic == "TAIL_RISK":
            start_date = period_start(request)
            snapshot.nav_returns = [item for item in snapshot.nav_returns if item[0] >= start_date]
            bound = RiskEngine().bind(snapshot)
            kwargs["sigma_levels"] = request.sigma_levels
            kwargs["capital_buffer"] = snapshot.net_asset * request.capital_buffer_pct_nav / 100.0
        elif analytic == "KRD":
            kwargs["bump_bps"] = request.rate_bump_bps
        elif analytic == "PNL_EXPLAIN":
            start_date = period_start(request, 30)
            previous = await load_portfolio_snapshot(fund_id, start_date, db, request.lookback_days)
            kwargs["previous"] = previous
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
            kwargs["market"] = market
            kwargs["weight_mode"] = request.weight_mode.value if hasattr(request.weight_mode, "value") else request.weight_mode
            kwargs["custom_weights"] = request.custom_weights
        elif analytic == "VAR_BACKTEST":
            start_date = period_start(request)
            snapshot.nav_returns = [item for item in snapshot.nav_returns if item[0] >= start_date]
            bound = RiskEngine().bind(snapshot)
            kwargs["confidence"] = request.confidence
            kwargs["window"] = request.backtest_window
        elif analytic == "XVA":
            kwargs.update(
                {
                    "counterparty_hazard": request.counterparty_hazard,
                    "own_hazard": request.own_hazard,
                    "recovery_rate": request.recovery_rate,
                    "funding_spread": request.funding_spread,
                    "initial_margin_pct": request.initial_margin_pct,
                    "mva_funding_spread": request.mva_funding_spread,
                }
            )
        else:
            raise HTTPException(status_code=422, detail="Unsupported analytic")

        result = bound.risk().risk_testing(analytic, **kwargs)
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
    """Run one Risk Testing analytic on RiskEngine (offline / tests)."""

    bound = RiskEngine().bind(snapshot)
    key = str(analytic).upper()
    report = bound.risk().risk_testing(key, **kwargs)
    return _stamp_riskengine(report, snapshot, key)
