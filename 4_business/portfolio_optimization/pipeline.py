"""Optimization result must pass RiskEngine gates before any downstream use.

Optimization → RiskEngine → Valuation → Investment Risk → Risk Testing → Limits

The payload is a proposal. It is never a trade instruction.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from .domains import GATE

_engine = import_module("3_riskengine")
_ir = import_module("4_business.investment_risk.service")
_models = import_module("2_processing.tools.risk_testing.models")
_snapshots = import_module("4_business.portfolio_optimization.snapshots")

Shock = _models.Shock
RiskFactorType = _models.RiskFactorType
ShockMode = _models.ShockMode
SCENARIOS = import_module("2_processing.tools.risk_testing.scenarios").SCENARIOS

INVESTMENT_KPIS = ("VaR", "CVaR", "Risk Contribution", "Gross Exposure", "Liquidity", "Concentration", "Leverage")


def govern_proposal(
    snapshot: Any,
    weights: Mapping[str, float],
    *,
    method: str,
    optimization: Mapping[str, Any],
    constraints: Mapping[str, Any] | None = None,
    current_weights: Mapping[str, float] | None = None,
    returns: Any | None = None,
    risk_budgets: Mapping[str, float] | None = None,
    scenario_id: str = "gfc_2008",
) -> dict[str, Any]:
    proposed = _snapshots.apply_weights(snapshot, weights)
    bound = _engine.RiskEngine().bind(proposed)
    valuation = bound.valuation().price()
    investment = _ir.compute_kpi_pack(proposed)
    selected = {kpi: investment["kpis"][kpi] for kpi in INVESTMENT_KPIS if kpi in investment["kpis"]}
    shocks = (
        Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="equity +1%"),
        Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="rate +1bp"),
    )
    sensitivity = bound.risk().sensitivity(shocks)
    scenario = SCENARIOS.get(scenario_id) or next(iter(SCENARIOS.values()))
    stress = bound.risk().stress(scenario)
    validation = bound.validation().pricing()
    limits = bound.limits().check(
        weights,
        constraints=constraints,
        current_weights=current_weights or _snapshots.current_weights(snapshot),
        returns=returns,
        risk_budgets=risk_budgets,
    )
    gate_status = {
        "optimization": optimization.get("status") == "PROPOSAL" and bool(optimization.get("weights")),
        "riskengine": True,
        "valuation": valuation.base_pv > 0,
        "investment_risk": bool(selected),
        "risk_testing": sensitivity.get("analytic") == "SENSITIVITY",
        "limits": bool(limits.get("passed")),
    }
    ready = all(gate_status.values())
    return {
        "is_trade_instruction": False,
        "trade_instruction": None,
        "status": "PROPOSAL",
        "requires_authorization": True,
        "ready_for_review": ready,
        "method": method,
        "weights": dict(weights),
        "gate": list(GATE),
        "gate_status": gate_status,
        "optimization": dict(optimization),
        "valuation": {
            "base_pv": valuation.base_pv,
            "engine": valuation.context.get("engine"),
            "engine_version": valuation.context.get("engine_version"),
            "data_quality": valuation.context.get("data_quality"),
        },
        "investment_risk": {
            "fund_id": proposed.fund_id,
            "kpis": selected,
            "engine": investment.get("engine"),
        },
        "risk_testing": {
            "sensitivity": {
                "analytic": sensitivity.get("analytic"),
                "pnl": sensitivity.get("pnl"),
            },
            "stress": {
                "analytic": stress.get("analytic"),
                "pnl": stress.get("pnl"),
                "scenario_id": getattr(scenario, "scenario_id", scenario_id),
            },
        },
        "limits": limits,
        "validation": {
            "status": validation.status,
            "checks": validation.checks,
        },
        "proposed_snapshot": {
            "fund_id": proposed.fund_id,
            "is_live": False,
            "positions": len(proposed.positions),
            "net_asset": proposed.net_asset,
        },
    }
