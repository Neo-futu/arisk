"""Pre-trade risk: Order → proposed portfolio → valuation/risk/stress/limits."""
from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping

from .audit_log import AuditLog, default_audit
from .domains import DECISIONS, PRE_TRADE_GATE

_engine = import_module("3_riskengine")
_limits = import_module("3_riskengine.limits")
_kpis = import_module("3_riskengine.risk.kpis")
_models = import_module("2_processing.tools.risk_testing.models")
_proposed = import_module("4_business.trading.proposed")
SCENARIOS = import_module("2_processing.tools.risk_testing.scenarios").SCENARIOS

Shock = _models.Shock
RiskFactorType = _models.RiskFactorType
ShockMode = _models.ShockMode
RiskEngine = _engine.RiskEngine


def decision_from_state(state: str, *, exception_approved: bool = False) -> str:
    if state == "HARD_BREACH":
        return "REJECT"
    if state == "BREACH":
        return "WARNING" if exception_approved else "REJECT"
    if state == "WARNING":
        return "WARNING"
    return "APPROVE"


def run_pre_trade(
    snapshot: Any,
    order: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
    scenario_id: str = "gfc_2008",
    exception_approved: bool = False,
    actor: str = "system",
    audit: AuditLog | None = None,
) -> dict[str, Any]:
    proposed = _proposed.apply_proposed_trade(snapshot, order)
    bound = RiskEngine().bind(proposed)
    valuation = bound.valuation().price()
    shocks = (
        Shock(RiskFactorType.EQUITY, 0.01, ShockMode.RELATIVE, label="equity +1%"),
        Shock(RiskFactorType.RATE, 0.0001, ShockMode.ABSOLUTE, label="rate +1bp"),
    )
    risk = bound.risk().sensitivity(shocks)
    scenario = SCENARIOS.get(scenario_id) or next(iter(SCENARIOS.values()))
    stress = bound.risk().stress(scenario)
    selected = _kpis.compute_selected(
        proposed,
        ("Liquidity", "Concentration", "Counterparty Exposure", "VaR", "CVaR", "Gross Exposure"),
    )
    limits = _limits.evaluate(proposed, policy=policy)
    state = limits["state"]
    decision = decision_from_state(state, exception_approved=exception_approved)
    if decision not in DECISIONS:
        decision = "REJECT"
    payload = {
        "decision": decision,
        "state": state,
        "gate": list(PRE_TRADE_GATE),
        "is_trade_instruction": False,
        "requires_authorization": decision != "APPROVE",
        "exception_approved": exception_approved,
        "order": {
            "security_code": order.get("security_code"),
            "side": str(order.get("side") or "BUY").upper(),
            "amount": float(order["amount"]),
            "asset_class": order.get("asset_class"),
        },
        "current": {
            "fund_id": snapshot.fund_id,
            "net_asset": snapshot.net_asset,
            "positions": len(snapshot.positions),
        },
        "proposed": {
            "fund_id": proposed.fund_id,
            "net_asset": proposed.net_asset,
            "positions": len(proposed.positions),
            "is_live": False,
        },
        "valuation": {
            "base_pv": valuation.base_pv,
            "engine": valuation.context.get("engine"),
        },
        "risk": {"analytic": risk.get("analytic"), "pnl": risk.get("pnl")},
        "stress": {
            "analytic": stress.get("analytic"),
            "pnl": stress.get("pnl"),
            "scenario_id": getattr(scenario, "scenario_id", scenario_id),
        },
        "liquidity": selected["Liquidity"]["result"],
        "concentration": selected["Concentration"]["result"],
        "counterparty": selected["Counterparty Exposure"]["result"],
        "limit": limits,
        "engine": "3_riskengine.limits",
    }
    (audit or default_audit()).record(
        "PRE_TRADE",
        actor=actor,
        payload={"decision": decision, "state": state, "order": payload["order"]},
    )
    return payload
