"""Portfolio optimization use-case layer.

Business → RiskEngine → Riskfolio adapter. Existing /portfolio-opt analyze
payloads stay on the legacy PyPortfolioOpt engine via compat.
"""
from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from .domains import GATE, MODULES, OPTIMIZERS, SUPPORT
from .pipeline import govern_proposal
from .simulation.store import LivePortfolioLocked, SimulationStore, default_store
from .snapshots import apply_weights, current_weights, snapshot_from_weights

_engine = import_module("3_riskengine")
_optimizer = import_module("2_processing.tools.performance.portfolio_optimizer")
_loader = import_module("2_processing.tools.risk_testing.loader")
_limits = import_module("3_riskengine.limits")
_ir = import_module("4_business.investment_risk.service")

RiskEngine = _engine.RiskEngine


def catalog() -> dict[str, Any]:
    status = RiskEngine().adapters_status()
    return {
        "module": "portfolio_optimization",
        "engine": status["engine"],
        "engine_version": status["engine_version"],
        "primary_adapter": "riskfolio",
        "adapters": status,
        "methods": list(OPTIMIZERS),
        "support": list(SUPPORT),
        "modules": list(MODULES),
        "gate": list(GATE),
        "is_trade_instruction": False,
        "frontend_routes": "/portfolio-opt",
        "data": ["fsi.balance_*", "fsi.mktdata_*"],
        "simulation": {
            "flow": ["live", "clone", "modify", "optimize", "stress", "compare"],
            "live_write": "authorization_required",
        },
    }


def synthetic_returns(tickers: list[str], lookback_days: int = 400) -> Any:
    prices = _optimizer.build_synthetic_prices(tickers, lookback_days)
    return prices.pct_change().dropna()


def optimize(
    returns: Any,
    method: str,
    *,
    constraints: Mapping[str, Any] | None = None,
    current_weights: Mapping[str, float] | None = None,
    views: Mapping[str, float] | None = None,
    risk_budgets: Mapping[str, float] | None = None,
    confidence: float = 0.95,
) -> dict[str, Any]:
    adapter = RiskEngine().riskfolio
    return adapter.optimize(
        returns,
        method,
        constraints=constraints,
        current_weights=current_weights,
        views=views,
        risk_budgets=risk_budgets,
        confidence=confidence,
    )


def optimize_and_govern(
    snapshot: Any,
    method: str,
    *,
    returns: Any | None = None,
    constraints: Mapping[str, Any] | None = None,
    views: Mapping[str, float] | None = None,
    risk_budgets: Mapping[str, float] | None = None,
    confidence: float = 0.95,
    scenario_id: str = "gfc_2008",
) -> dict[str, Any]:
    tickers = [p.security_code for p in snapshot.positions]
    panel = returns if returns is not None else synthetic_returns(tickers)
    live_weights = current_weights(snapshot)
    optimization = optimize(
        panel,
        method,
        constraints=constraints,
        current_weights=live_weights,
        views=views,
        risk_budgets=risk_budgets,
        confidence=confidence,
    )
    return govern_proposal(
        snapshot,
        optimization["weights"],
        method=method,
        optimization=optimization,
        constraints=constraints,
        current_weights=live_weights,
        returns=panel,
        risk_budgets=risk_budgets,
        scenario_id=scenario_id,
    )


def risk_contribution(weights: Mapping[str, float], returns: Any) -> dict[str, float]:
    return RiskEngine().riskfolio.risk_contribution(weights, returns)


def check_constraints(
    weights: Mapping[str, float],
    *,
    constraints: Mapping[str, Any] | None = None,
    current_weights: Mapping[str, float] | None = None,
    returns: Any | None = None,
    risk_budgets: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    return _limits.check(
        weights,
        constraints=constraints,
        current_weights=current_weights,
        returns=returns,
        risk_budgets=risk_budgets,
    )


def clone_live(
    snapshot: Any,
    *,
    label: str = "",
    store: SimulationStore | None = None,
) -> dict[str, Any]:
    return (store or default_store()).clone_live(snapshot, label=label)


def modify_simulation(
    sim_id: str,
    weights: Mapping[str, float],
    *,
    target: str = "simulation",
    authorized: bool = False,
    store: SimulationStore | None = None,
) -> dict[str, Any]:
    return (store or default_store()).modify(
        sim_id,
        weights,
        target=target,
        authorized=authorized,
    )


def optimize_simulation(
    sim_id: str,
    method: str,
    *,
    store: SimulationStore | None = None,
    constraints: Mapping[str, Any] | None = None,
    views: Mapping[str, float] | None = None,
    risk_budgets: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    active = store or default_store()
    record = active.get(sim_id)
    review = optimize_and_govern(
        record["snapshot"],
        method,
        constraints=constraints,
        views=views,
        risk_budgets=risk_budgets,
    )
    active.attach_review(sim_id, review)
    return {"simulation": active.public(active.get(sim_id)), "review": review}


def stress_simulation(
    sim_id: str,
    *,
    store: SimulationStore | None = None,
    scenario_id: str = "gfc_2008",
) -> dict[str, Any]:
    active = store or default_store()
    record = active.get(sim_id)
    scenarios = import_module("2_processing.tools.risk_testing.scenarios").SCENARIOS
    scenario = scenarios.get(scenario_id) or next(iter(scenarios.values()))
    report = RiskEngine().bind(record["snapshot"]).risk().stress(scenario)
    payload = {
        "analytic": report.get("analytic"),
        "pnl": report.get("pnl"),
        "scenario_id": scenario_id,
        "is_trade_instruction": False,
    }
    active.attach_stress(sim_id, payload)
    return {"simulation": active.public(active.get(sim_id)), "stress": payload}


def compare_simulation(sim_id: str, *, store: SimulationStore | None = None) -> dict[str, Any]:
    active = store or default_store()
    compared = active.compare(sim_id)
    record = active.get(sim_id)
    live_pack = _ir.compute_kpi_pack(record["live_snapshot"])
    sim_pack = _ir.compute_kpi_pack(record["snapshot"])
    compared["live_valuation_nav"] = record["live_snapshot"].net_asset
    compared["sim_valuation_nav"] = record["snapshot"].net_asset
    compared["kpi_compare"] = {
        kpi: {
            "live": live_pack["kpis"][kpi]["result"],
            "simulation": sim_pack["kpis"][kpi]["result"],
        }
        for kpi in ("VaR", "CVaR", "Risk Contribution", "Concentration")
        if kpi in live_pack["kpis"]
    }
    return compared


def apply_to_live(sim_id: str, *, authorized: bool = False, store: SimulationStore | None = None) -> dict[str, Any]:
    return (store or default_store()).apply_to_live(sim_id, authorized=authorized)


async def load_snapshot(fund_id: str, as_of_date: date, db: AsyncSession, lookback_days: int = 500):
    return await _loader.load_portfolio_snapshot(fund_id, as_of_date, db, lookback_days)


# Re-exports used by thin domain modules
apply_weights = apply_weights
snapshot_from_weights = snapshot_from_weights
current_weights = current_weights
