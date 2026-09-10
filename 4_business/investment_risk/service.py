"""Investment Risk Analytics use-case layer.

Business → RiskEngine → FinancePy / Riskfolio / ORE.
Existing page APIs still return their original payloads via the legacy analysis
module. Unified KPI packs are additive.
"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from .domains import MODULE_KPIS

_analysis = import_module("2_processing.tools.performance.investment_analysis")
_loader = import_module("2_processing.tools.risk_testing.loader")
_kpis = import_module("3_riskengine.risk.kpis")
_engine = import_module("3_riskengine")


async def load_snapshot(fund_id: str, as_of_date: date, db: AsyncSession, lookback_days: int = 500):
    return await _loader.load_portfolio_snapshot(fund_id, as_of_date, db, lookback_days)


def kpi_catalog() -> dict[str, Any]:
    status = _engine.RiskEngine().adapters_status()
    return {
        "module": "investment_risk",
        "engine": status["engine"],
        "engine_version": status["engine_version"],
        "adapters": status,
        "kpis": list(_kpis.KPI_IDS),
        "domains": {name: list(ids) for name, ids in MODULE_KPIS.items()},
        "frontend_routes": "/investment-risk/*",
        "data": ["fsi.balance_*", "fsi.mktdata_*"],
        "limit_engine": "3_riskengine.limits",
    }


def compute_kpi_pack(
    snapshot: Any,
    *,
    confidence: float = 0.99,
    benchmark_returns: Iterable[float] | None = None,
) -> dict[str, Any]:
    pack = _kpis.compute_kpi_pack(
        snapshot,
        confidence=confidence,
        benchmark_returns=benchmark_returns,
    )
    pack["domains"] = {
        name: {
            "domain": name,
            "kpis": {kpi_id: pack["kpis"][kpi_id] for kpi_id in ids},
            "engine": "ARISK RiskEngine",
        }
        for name, ids in MODULE_KPIS.items()
    }
    limits = import_module("3_riskengine.limits")
    pack["limits"] = limits.evaluate(snapshot)
    pack["limit_engine"] = "3_riskengine.limits"
    pack["adapters"] = _engine.RiskEngine().adapters_status()
    return pack


async def kpi_pack_for_fund(
    fund_id: str,
    as_of_date: date,
    db: AsyncSession,
    *,
    confidence: float = 0.99,
    lookback_days: int = 500,
) -> dict[str, Any]:
    snapshot = await load_snapshot(fund_id, as_of_date, db, lookback_days)
    return compute_kpi_pack(snapshot, confidence=confidence)


# Legacy page contracts — unchanged payloads, now invoked from the business layer.

compute_portfolio_basic_info = _analysis.compute_portfolio_basic_info
compute_portfolio_overview = _analysis.compute_portfolio_overview
compute_portfolio_overview_timeseries = _analysis.compute_portfolio_overview_timeseries
compute_risk_indicators = _analysis.compute_risk_indicators
compute_risk_indicator_timeseries = _analysis.compute_risk_indicator_timeseries
compute_performance_attribution = _analysis.compute_performance_attribution
compute_performance_attribution_timeseries = _analysis.compute_performance_attribution_timeseries
compute_rates_credit_sensitivity = _analysis.compute_rates_credit_sensitivity
compute_liquidity_stress_testing = _analysis.compute_liquidity_stress_testing
compute_pretrade_risk_budget = _analysis.compute_pretrade_risk_budget
compute_macro_market_dynamics = _analysis.compute_macro_market_dynamics
compute_factor_behavior_risk = _analysis.compute_factor_behavior_risk
